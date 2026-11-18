"""Application services that coordinate engagement-core domain logic."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import date
from typing import Any, TypeVar

from redscribe.v2.engagements.coverage import (
    compute_coverage,
    coverage_gap_summary,
    coverage_percent,
    criticality_distribution,
    out_of_scope_count,
)
from redscribe.v2.engagements.cvss import cvss_base_score, cvss_breakdown, severity_agreement
from redscribe.v2.engagements.duplicates import (
    best_duplicate,
    cluster_duplicates,
    duplicate_summary,
    find_duplicates,
)
from redscribe.v2.engagements.errors import (
    EngagementError,
    EngagementErrorCode,
    not_found,
    validation_error,
)
from redscribe.v2.engagements.models import (
    CONFIDENCE_ORDER,
    Activity,
    ActivityAction,
    Asset,
    AssetKind,
    AssetStatus,
    Confidence,
    Credential,
    CredentialKind,
    CredentialStatus,
    Criticality,
    Engagement,
    EngagementKind,
    EngagementStatus,
    Entity,
    Finding,
    FindingEvent,
    FindingStatus,
    ScopeAction,
    ScopeRule,
    ScopeRuleKind,
    ScopeStatus,
    ServiceStatus,
    Severity,
    Target,
    TargetKind,
    TargetStatus,
    severity_index,
)
from redscribe.v2.engagements.models import (
    Service as ServiceEntity,
)
from redscribe.v2.engagements.repositories import (
    EngagementStore,
    Repository,
    RepositoryError,
    seed_demo,
)
from redscribe.v2.engagements.rollups import (
    engagement_rollup,
    portfolio_rollup,
    severity_matrix,
    widget_cards,
)
from redscribe.v2.engagements.state_machine import (
    CREDENTIAL_MACHINE,
    ENGAGEMENT_MACHINE,
    FINDING_MACHINE,
    SCOPE_MACHINE,
    SERVICE_MACHINE,
    TARGET_MACHINE,
    TransitionError,
    describe_workflows,
    transition_context,
)
from redscribe.v2.engagements.util import dedupe, now_iso, slugify, truncate
from redscribe.v2.engagements.validation import (
    ValidationReport,
    detect_target_kind,
    engagement_patch_report,
    finding_patch_report,
    normalize_cwe,
    optional_id,
    optional_text,
    require_id,
    require_text,
    severity_for_score,
    validate_cves,
    validate_cvss_vector,
    validate_iso_date,
    validate_port,
    validate_protocol,
    validate_references,
    validate_scope_expression,
    validate_tags,
    validate_target_value,
)

EntityT = TypeVar("EntityT", bound=Entity)


class EngagementService:
    """Use cases for engagements, targets, assets, services, and findings."""

    def __init__(self, store: EngagementStore | None = None, *, actor: str = "local") -> None:
        self.store = store if store is not None else EngagementStore()
        self.actor = actor

    # ------------------------------------------------------------------
    # Shared helpers
    # ------------------------------------------------------------------

    def _require_engagement(self, engagement_id: int) -> Engagement:
        engagement = self.store.engagements.get(engagement_id)
        if engagement is None:
            raise not_found("engagement", engagement_id)
        return engagement

    def _require_in(
        self,
        repository: Repository[EntityT],
        entity_id: int,
        *,
        name: str,
        engagement_id: int | None = None,
    ) -> EntityT:
        try:
            entity = repository.require(entity_id)
        except RepositoryError as exc:
            raise not_found(name, entity_id) from exc
        if engagement_id is not None and entity.engagement_id != engagement_id:
            raise not_found(name, entity_id)
        return entity

    @staticmethod
    def _raise_if_invalid(report: ValidationReport) -> None:
        if not report.ok:
            raise validation_error([issue.as_dict() for issue in report.errors])

    def _log(
        self,
        engagement_id: int,
        entity_type: str,
        entity_id: int,
        action: ActivityAction,
        summary: str,
    ) -> None:
        self.store.activities.add(
            Activity(
                engagement_id=engagement_id,
                entity_type=entity_type,
                entity_id=entity_id,
                action=action,
                summary=truncate(summary, limit=200),
                actor=self.actor,
                created_at=now_iso(),
            )
        )

    def _require_target(self, engagement_id: int, target_id: int) -> Target:
        return self._require_in(
            self.store.targets,
            target_id,
            name="target",
            engagement_id=engagement_id,
        )

    def _require_asset(self, engagement_id: int, asset_id: int) -> Asset:
        return self._require_in(
            self.store.assets,
            asset_id,
            name="asset",
            engagement_id=engagement_id,
        )

    def _require_service(self, engagement_id: int, service_id: int) -> ServiceEntity:
        return self._require_in(
            self.store.services,
            service_id,
            name="service",
            engagement_id=engagement_id,
        )

    @staticmethod
    def _optional_relation(data: Mapping[str, Any], key: str, report: ValidationReport) -> int:
        return optional_id(data.get(key), key, report)

    # ------------------------------------------------------------------
    # Engagement use cases
    # ------------------------------------------------------------------

    def create_engagement(self, data: Mapping[str, Any]) -> dict[str, Any]:
        """Create an engagement from a validated request payload."""
        payload = dict(data)
        name = require_text(payload.get("name"), "name", ValidationReport())
        if "key" not in payload or not payload.get("key"):
            payload["key"] = slugify(name, fallback="engagement")
        report = engagement_patch_report(payload, partial=False)
        start_date = validate_iso_date(payload.get("start_date"), "start_date", report)
        end_date = validate_iso_date(payload.get("end_date"), "end_date", report)
        client = optional_text(payload.get("client"), "client", report)
        description = optional_text(
            payload.get("description"), "description", report, max_length=20000
        )
        owner = optional_text(payload.get("owner"), "owner", report)
        tags = validate_tags(payload.get("tags"), report)
        self._raise_if_invalid(report)
        key = str(payload["key"])
        if any(item.key.casefold() == key.casefold() for item in self.store.engagements.all()):
            raise EngagementError(
                f"Engagement key '{key}' is already in use",
                code=EngagementErrorCode.CONFLICT,
                status=409,
                details={"field": "key"},
            )
        if start_date and end_date and end_date < start_date:
            raise EngagementError(
                "end_date must be on or after start_date",
                code=EngagementErrorCode.VALIDATION,
                details={"field": "end_date"},
            )
        engagement = self.store.engagements.add(
            Engagement(
                key=key,
                name=str(payload["name"]).strip(),
                client=client,
                description=description,
                kind=EngagementKind(str(payload.get("kind", EngagementKind.PENTEST.value))),
                status=EngagementStatus(
                    str(payload.get("status", EngagementStatus.PLANNING.value))
                ),
                owner=owner,
                start_date=start_date,
                end_date=end_date,
                tags=tags,
                created_at=now_iso(),
                updated_at=now_iso(),
            )
        )
        self._log(
            engagement.id,
            "engagement",
            engagement.id,
            ActivityAction.CREATED,
            f"Created engagement {engagement.display_name}",
        )
        return self.engagement_detail(engagement.id)

    def update_engagement(self, engagement_id: int, data: Mapping[str, Any]) -> dict[str, Any]:
        """Apply a partial metadata update to an engagement."""
        self._require_engagement(engagement_id)
        report = engagement_patch_report(data, partial=True)
        self._raise_if_invalid(report)
        changes: dict[str, Any] = {}
        for field_name in ("name", "client", "description", "owner"):
            if field_name in data:
                changes[field_name] = str(data[field_name]).strip()
        if "key" in data:
            key = str(data["key"])
            if any(
                item.key.casefold() == key.casefold() and item.id != engagement_id
                for item in self.store.engagements.all()
            ):
                raise EngagementError(
                    f"Engagement key '{key}' is already in use",
                    code=EngagementErrorCode.CONFLICT,
                    status=409,
                    details={"field": "key"},
                )
            changes["key"] = key
        if "kind" in data:
            changes["kind"] = EngagementKind(str(data["kind"]))
        if "status" in data:
            changes["status"] = EngagementStatus(str(data["status"]))
        if "tags" in data:
            changes["tags"] = validate_tags(data["tags"], report)
        if "start_date" in data:
            changes["start_date"] = validate_iso_date(data["start_date"], "start_date", report)
        if "end_date" in data:
            changes["end_date"] = validate_iso_date(data["end_date"], "end_date", report)
        changes["updated_at"] = now_iso()
        updated = self.store.engagements.update(engagement_id, changes)
        self._log(
            engagement_id,
            "engagement",
            engagement_id,
            ActivityAction.UPDATED,
            f"Updated engagement fields: {', '.join(sorted(changes))}",
        )
        return self.engagement_detail(updated.id)

    def transition_engagement(
        self,
        engagement_id: int,
        action: str,
        *,
        note: str = "",
        report_signed_off: bool = False,
    ) -> dict[str, Any]:
        """Move an engagement through its lifecycle."""
        engagement = self._require_engagement(engagement_id)
        context = transition_context(
            note=note,
            report_signed_off=report_signed_off,
        )
        try:
            target = ENGAGEMENT_MACHINE.apply(engagement.status.value, action, context)
        except TransitionError as exc:
            raise EngagementError(
                str(exc),
                code=EngagementErrorCode.TRANSITION,
                status=409,
                details={"action": action, "from": engagement.status.value},
            ) from exc
        updated = self.store.engagements.update(
            engagement_id,
            {"status": EngagementStatus(target), "updated_at": now_iso()},
        )
        self._log(
            engagement_id,
            "engagement",
            engagement_id,
            ActivityAction.TRANSITIONED,
            f"{engagement.status.value} -> {target} ({action})",
        )
        return self.engagement_detail(updated.id)

    def engagement_detail(self, engagement_id: int) -> dict[str, Any]:
        """Return an engagement with relationship counts."""
        engagement = self._require_engagement(engagement_id)
        data = engagement.as_dict()
        data["counts"] = {
            "targets": len(self.store.targets.filter_by_engagement(engagement_id)),
            "assets": len(self.store.assets.filter_by_engagement(engagement_id)),
            "services": len(self.store.services.filter_by_engagement(engagement_id)),
            "credentials": len(self.store.credentials.filter_by_engagement(engagement_id)),
            "findings": len(self.store.findings.filter_by_engagement(engagement_id)),
            "scope_rules": len(self.store.scope_rules.filter_by_engagement(engagement_id)),
        }
        data["allowed_actions"] = list(ENGAGEMENT_MACHINE.allowed_actions(engagement.status.value))
        return data

    def list_engagements(
        self,
        *,
        status: str = "",
        kind: str = "",
        query: str = "",
        owner: str = "",
    ) -> list[dict[str, Any]]:
        """List engagements with simple server-side filters."""
        result: list[dict[str, Any]] = []
        needle = query.strip().casefold()
        for engagement in self.store.engagements.all():
            if status and engagement.status.value != status:
                continue
            if kind and engagement.kind.value != kind:
                continue
            if owner and engagement.owner.casefold() != owner.casefold():
                continue
            if (
                needle
                and needle
                not in " ".join(
                    [engagement.name, engagement.client, engagement.description, engagement.key]
                ).casefold()
            ):
                continue
            result.append(self.engagement_detail(engagement.id))
        return result

    def delete_engagement(self, engagement_id: int) -> dict[str, Any]:
        """Delete an engagement and all dependent entities."""
        engagement = self._require_engagement(engagement_id)
        for name, repository in self.store.repositories().items():
            if name == "engagements":
                if repository.exists(engagement_id):
                    repository.delete(engagement_id)
                continue
            for entity in repository.filter_by_engagement(engagement_id):
                repository.delete(entity.id)
        return {"id": engagement.id, "key": engagement.key, "deleted": True}

    # ------------------------------------------------------------------
    # Scope rule use cases
    # ------------------------------------------------------------------

    def add_scope_rule(self, engagement_id: int, data: Mapping[str, Any]) -> dict[str, Any]:
        """Add an include or exclude rule to an engagement scope."""
        self._require_engagement(engagement_id)
        report = ValidationReport()
        rule_kind, value, action = validate_scope_expression(
            data.get("kind", ScopeRuleKind.KEYWORD.value),
            data.get("value"),
            data.get("action", ScopeAction.INCLUDE.value),
            report,
        )
        self._raise_if_invalid(report)
        rule = self.store.scope_rules.add(
            ScopeRule(
                engagement_id=engagement_id,
                kind=rule_kind,
                value=value,
                action=action,
                notes=optional_text(data.get("notes"), "notes", report),
            )
        )
        self._log(
            engagement_id,
            "scope_rule",
            rule.id,
            ActivityAction.CREATED,
            f"Added {action.value} rule for {value}",
        )
        return rule.as_dict()

    def list_scope_rules(self, engagement_id: int) -> list[dict[str, Any]]:
        """Return scope rules ordered by id."""
        self._require_engagement(engagement_id)
        return [
            rule.as_dict() for rule in self.store.scope_rules.filter_by_engagement(engagement_id)
        ]

    def remove_scope_rule(self, engagement_id: int, rule_id: int) -> dict[str, Any]:
        """Remove one scope rule."""
        rule = self._require_in(
            self.store.scope_rules,
            rule_id,
            name="scope rule",
            engagement_id=engagement_id,
        )
        self.store.scope_rules.delete(rule_id)
        self._log(
            engagement_id, "scope_rule", rule_id, ActivityAction.DELETED, "Removed scope rule"
        )
        return rule.as_dict()

    def evaluate_scope(self, engagement_id: int, value: str) -> dict[str, Any]:
        """Evaluate a host or label against the engagement scope rules."""
        self._require_engagement(engagement_id)
        report = ValidationReport()
        cleaned = require_text(value, "value", report)
        self._raise_if_invalid(report)
        matched: list[dict[str, Any]] = []
        excluded = False
        included = False
        needle = cleaned.casefold()
        for rule in self.store.scope_rules.filter_by_engagement(engagement_id):
            rule_value = rule.value.casefold()
            if rule.kind is ScopeRuleKind.PORT:
                matches = rule_value in needle.split(":") or f":{rule_value}" in needle
            else:
                matches = rule_value in needle or needle in rule_value
            if not matches:
                continue
            matched.append(rule.as_dict())
            if rule.action is ScopeAction.EXCLUDE:
                excluded = True
            else:
                included = True
        decision = "excluded" if excluded else "included" if included else "unspecified"
        return {
            "engagement_id": engagement_id,
            "value": cleaned,
            "decision": decision,
            "in_scope": decision == "included",
            "matched": matched,
        }

    def suggest_scope_status(self, engagement_id: int, value: str) -> ScopeStatus:
        """Suggest a scope status from evaluated rules."""
        decision = self.evaluate_scope(engagement_id, value)["decision"]
        if decision == "included":
            return ScopeStatus.IN_SCOPE
        if decision == "excluded":
            return ScopeStatus.OUT_OF_SCOPE
        return ScopeStatus.PENDING

    def import_scope_rules(
        self, engagement_id: int, rules: Iterable[Mapping[str, Any]]
    ) -> dict[str, Any]:
        """Import a batch of scope rules, skipping exact duplicates."""
        created: list[dict[str, Any]] = []
        skipped = 0
        existing = {
            (rule.kind.value, rule.value.casefold(), rule.action.value)
            for rule in self.store.scope_rules.filter_by_engagement(engagement_id)
        }
        for rule_data in rules:
            key = (
                str(rule_data.get("kind", ScopeRuleKind.KEYWORD.value)),
                str(rule_data.get("value", "")).casefold(),
                str(rule_data.get("action", ScopeAction.INCLUDE.value)),
            )
            if key in existing:
                skipped += 1
                continue
            created.append(self.add_scope_rule(engagement_id, rule_data))
            existing.add(key)
        return {"created": created, "skipped": skipped, "total": len(created)}

    # ------------------------------------------------------------------
    # Target use cases
    # ------------------------------------------------------------------

    def add_target(self, engagement_id: int, data: Mapping[str, Any]) -> dict[str, Any]:
        """Create a target in an engagement."""
        self._require_engagement(engagement_id)
        report = ValidationReport()
        value = validate_target_value(data.get("value"), report)
        kind = TargetKind(str(data["kind"])) if "kind" in data else detect_target_kind(value)
        scope_status = (
            ScopeStatus(str(data["scope_status"]))
            if "scope_status" in data
            else self.suggest_scope_status(engagement_id, value)
        )
        if any(
            target.value.casefold() == value.casefold()
            for target in self.store.targets.filter_by_engagement(engagement_id)
        ):
            raise EngagementError(
                f"Target '{value}' already exists in this engagement",
                code=EngagementErrorCode.CONFLICT,
                status=409,
                details={"field": "value"},
            )
        target_name = optional_text(data.get("name"), "name", report)
        description = optional_text(data.get("description"), "description", report)
        tags = validate_tags(data.get("tags"), report)
        notes = optional_text(data.get("notes"), "notes", report)
        self._raise_if_invalid(report)
        target = self.store.targets.add(
            Target(
                engagement_id=engagement_id,
                value=value,
                name=target_name,
                kind=kind,
                description=description,
                status=TargetStatus(str(data.get("status", TargetStatus.DISCOVERED.value))),
                scope_status=scope_status,
                criticality=Criticality(str(data.get("criticality", Criticality.MEDIUM.value))),
                tags=tags,
                notes=notes,
                created_at=now_iso(),
                updated_at=now_iso(),
            )
        )
        self._log(
            engagement_id, "target", target.id, ActivityAction.CREATED, f"Added target {value}"
        )
        return target.as_dict()

    def update_target(self, target_id: int, data: Mapping[str, Any]) -> dict[str, Any]:
        """Apply a partial update to a target."""
        existing = self._require_in(self.store.targets, target_id, name="target")
        report = ValidationReport()
        changes: dict[str, Any] = {}
        if "value" in data:
            changes["value"] = validate_target_value(data["value"], report)
        for name in ("name", "description", "notes"):
            if name in data:
                changes[name] = optional_text(data[name], name, report)
        if "kind" in data:
            changes["kind"] = TargetKind(str(data["kind"]))
        if "status" in data:
            changes["status"] = TargetStatus(str(data["status"]))
        if "scope_status" in data:
            changes["scope_status"] = ScopeStatus(str(data["scope_status"]))
        if "criticality" in data:
            changes["criticality"] = Criticality(str(data["criticality"]))
        if "tags" in data:
            changes["tags"] = validate_tags(data["tags"], report)
        self._raise_if_invalid(report)
        changes["updated_at"] = now_iso()
        updated = self.store.targets.update(target_id, changes)
        self._log(
            existing.engagement_id,
            "target",
            target_id,
            ActivityAction.UPDATED,
            f"Updated target fields: {', '.join(sorted(changes))}",
        )
        return updated.as_dict()

    def remove_target(self, target_id: int) -> dict[str, Any]:
        """Delete a target and its dependent assets, services, and credentials."""
        target = self._require_in(self.store.targets, target_id, name="target")
        for repository in (self.store.assets, self.store.services, self.store.credentials):
            for entity in repository.where(lambda item: getattr(item, "target_id", 0) == target_id):
                repository.delete(entity.id)
        self.store.targets.delete(target_id)
        self._log(
            target.engagement_id, "target", target_id, ActivityAction.DELETED, "Deleted target"
        )
        return target.as_dict()

    def transition_target(self, target_id: int, action: str, *, reason: str = "") -> dict[str, Any]:
        """Move a target through its lifecycle."""
        target = self._require_in(self.store.targets, target_id, name="target")
        context = transition_context(reason=reason)
        try:
            next_state = TARGET_MACHINE.apply(target.status.value, action, context)
        except TransitionError as exc:
            raise EngagementError(
                str(exc),
                code=EngagementErrorCode.TRANSITION,
                status=409,
                details={"action": action, "from": target.status.value},
            ) from exc
        changes: dict[str, Any] = {"status": TargetStatus(next_state), "updated_at": now_iso()}
        if next_state == TargetStatus.EXCLUDED.value and reason:
            changes["notes"] = f"{target.notes}\nExcluded: {reason}".strip()
        updated = self.store.targets.update(target_id, changes)
        self._log(
            target.engagement_id,
            "target",
            target_id,
            ActivityAction.TRANSITIONED,
            f"{target.status.value} -> {next_state} ({action})",
        )
        return updated.as_dict()

    def transition_target_scope(self, target_id: int, action: str) -> dict[str, Any]:
        """Move a target through manual scope review."""
        target = self._require_in(self.store.targets, target_id, name="target")
        try:
            next_state = SCOPE_MACHINE.apply(target.scope_status.value, action)
        except TransitionError as exc:
            raise EngagementError(
                str(exc),
                code=EngagementErrorCode.TRANSITION,
                status=409,
                details={"action": action, "from": target.scope_status.value},
            ) from exc
        updated = self.store.targets.update(
            target_id,
            {"scope_status": ScopeStatus(next_state), "updated_at": now_iso()},
        )
        self._log(
            target.engagement_id,
            "target",
            target_id,
            ActivityAction.REVIEWED,
            f"Scope {target.scope_status.value} -> {next_state}",
        )
        return updated.as_dict()

    def list_targets(
        self,
        engagement_id: int,
        *,
        scope_status: str = "",
        status: str = "",
        query: str = "",
        criticality: str = "",
    ) -> list[dict[str, Any]]:
        """List targets with filters."""
        self._require_engagement(engagement_id)
        needle = query.strip().casefold()
        result: list[dict[str, Any]] = []
        for target in self.store.targets.filter_by_engagement(engagement_id):
            if scope_status and target.scope_status.value != scope_status:
                continue
            if status and target.status.value != status:
                continue
            if criticality and target.criticality.value != criticality:
                continue
            if (
                needle
                and needle
                not in " ".join(
                    [target.value, target.name, target.description, " ".join(target.tags)]
                ).casefold()
            ):
                continue
            result.append(target.as_dict())
        return result

    # ------------------------------------------------------------------
    # Asset use cases
    # ------------------------------------------------------------------

    def add_asset(self, engagement_id: int, data: Mapping[str, Any]) -> dict[str, Any]:
        """Create an asset attached to a target."""
        self._require_engagement(engagement_id)
        report = ValidationReport()
        target_id = require_id(data.get("target_id"), "target_id", report)
        self._raise_if_invalid(report)
        self._require_target(engagement_id, target_id)
        name = require_text(data.get("name"), "name", report)
        identifier = optional_text(data.get("identifier"), "identifier", report)
        owner = optional_text(data.get("owner"), "owner", report)
        notes = optional_text(data.get("notes"), "notes", report)
        self._raise_if_invalid(report)
        asset = self.store.assets.add(
            Asset(
                engagement_id=engagement_id,
                target_id=target_id,
                name=name,
                kind=AssetKind(str(data.get("kind", AssetKind.UNKNOWN.value))),
                identifier=identifier,
                status=AssetStatus(str(data.get("status", AssetStatus.IDENTIFIED.value))),
                criticality=Criticality(str(data.get("criticality", Criticality.MEDIUM.value))),
                owner=owner,
                notes=notes,
                created_at=now_iso(),
                updated_at=now_iso(),
            )
        )
        self._log(
            engagement_id, "asset", asset.id, ActivityAction.CREATED, f"Added asset {asset.name}"
        )
        return asset.as_dict()

    def update_asset(self, asset_id: int, data: Mapping[str, Any]) -> dict[str, Any]:
        """Apply a partial update to an asset."""
        existing = self._require_in(self.store.assets, asset_id, name="asset")
        report = ValidationReport()
        changes: dict[str, Any] = {}
        for name in ("name", "identifier", "owner", "notes"):
            if name in data:
                changes[name] = require_text(data[name], name, report, allow_empty=True)
        if "kind" in data:
            changes["kind"] = AssetKind(str(data["kind"]))
        if "status" in data:
            changes["status"] = AssetStatus(str(data["status"]))
        if "criticality" in data:
            changes["criticality"] = Criticality(str(data["criticality"]))
        if "target_id" in data:
            changes["target_id"] = require_id(data["target_id"], "target_id", report)
        self._raise_if_invalid(report)
        if "target_id" in changes:
            self._require_target(existing.engagement_id, changes["target_id"])
        changes["updated_at"] = now_iso()
        updated = self.store.assets.update(asset_id, changes)
        self._log(
            existing.engagement_id,
            "asset",
            asset_id,
            ActivityAction.UPDATED,
            f"Updated asset fields: {', '.join(sorted(changes))}",
        )
        return updated.as_dict()

    def remove_asset(self, asset_id: int) -> dict[str, Any]:
        """Delete an asset and clear references from services and findings."""
        asset = self._require_in(self.store.assets, asset_id, name="asset")
        self.store.assets.delete(asset_id)
        for repository in (self.store.services, self.store.findings):
            for entity in repository.where(lambda item: getattr(item, "asset_id", 0) == asset_id):
                repository.update(entity.id, {"asset_id": 0})
        self._log(asset.engagement_id, "asset", asset_id, ActivityAction.DELETED, "Deleted asset")
        return asset.as_dict()

    def list_assets(
        self, engagement_id: int, *, target_id: int = 0, query: str = ""
    ) -> list[dict[str, Any]]:
        """List assets with filters."""
        self._require_engagement(engagement_id)
        needle = query.strip().casefold()
        return [
            asset.as_dict()
            for asset in self.store.assets.filter_by_engagement(engagement_id)
            if (not target_id or asset.target_id == target_id)
            and (
                not needle
                or needle in " ".join([asset.name, asset.identifier, asset.owner]).casefold()
            )
        ]

    # ------------------------------------------------------------------
    # Service use cases
    # ------------------------------------------------------------------

    def add_service(self, engagement_id: int, data: Mapping[str, Any]) -> dict[str, Any]:
        """Create a service attached to a target and optional asset."""
        self._require_engagement(engagement_id)
        report = ValidationReport()
        target_id = require_id(data.get("target_id"), "target_id", report)
        self._raise_if_invalid(report)
        self._require_target(engagement_id, target_id)
        asset_id = self._optional_relation(data, "asset_id", report)
        if asset_id:
            asset = self._require_asset(engagement_id, asset_id)
            if asset.target_id != target_id:
                raise EngagementError(
                    "asset_id belongs to a different target",
                    code=EngagementErrorCode.VALIDATION,
                    details={"field": "asset_id"},
                )
        name = require_text(data.get("name"), "name", report)
        port = validate_port(data.get("port"), report)
        protocol = validate_protocol(data.get("protocol", "tcp"), report)
        product = optional_text(data.get("product"), "product", report)
        version = optional_text(data.get("version"), "version", report)
        notes = optional_text(data.get("notes"), "notes", report)
        self._raise_if_invalid(report)
        service = self.store.services.add(
            ServiceEntity(
                engagement_id=engagement_id,
                target_id=target_id,
                asset_id=asset_id,
                name=name,
                port=port,
                protocol=protocol,
                product=product,
                version=version,
                status=ServiceStatus(str(data.get("status", ServiceStatus.DISCOVERED.value))),
                notes=notes,
                created_at=now_iso(),
                updated_at=now_iso(),
            )
        )
        self._log(
            engagement_id,
            "service",
            service.id,
            ActivityAction.CREATED,
            f"Added service {service.endpoint}",
        )
        return service.as_dict()

    def update_service(self, service_id: int, data: Mapping[str, Any]) -> dict[str, Any]:
        """Apply a partial update to a service."""
        existing = self._require_in(self.store.services, service_id, name="service")
        report = ValidationReport()
        changes: dict[str, Any] = {}
        for name in ("name", "product", "version", "notes"):
            if name in data:
                changes[name] = require_text(data[name], name, report, allow_empty=True)
        if "port" in data:
            changes["port"] = validate_port(data["port"], report)
        if "protocol" in data:
            changes["protocol"] = validate_protocol(data["protocol"], report)
        if "status" in data:
            changes["status"] = ServiceStatus(str(data["status"]))
        if "target_id" in data:
            changes["target_id"] = require_id(data["target_id"], "target_id", report)
        if "asset_id" in data:
            changes["asset_id"] = optional_id(data["asset_id"], "asset_id", report)
        self._raise_if_invalid(report)
        target_id = changes.get("target_id", existing.target_id)
        self._require_target(existing.engagement_id, target_id)
        changes["updated_at"] = now_iso()
        updated = self.store.services.update(service_id, changes)
        self._log(
            existing.engagement_id,
            "service",
            service_id,
            ActivityAction.UPDATED,
            f"Updated service fields: {', '.join(sorted(changes))}",
        )
        return updated.as_dict()

    def transition_service(self, service_id: int, action: str) -> dict[str, Any]:
        """Move a service through its verification lifecycle."""
        service = self._require_in(self.store.services, service_id, name="service")
        try:
            next_state = SERVICE_MACHINE.apply(service.status.value, action)
        except TransitionError as exc:
            raise EngagementError(
                str(exc),
                code=EngagementErrorCode.TRANSITION,
                status=409,
                details={"action": action, "from": service.status.value},
            ) from exc
        updated = self.store.services.update(
            service_id,
            {"status": ServiceStatus(next_state), "updated_at": now_iso()},
        )
        self._log(
            service.engagement_id,
            "service",
            service_id,
            ActivityAction.TRANSITIONED,
            f"{service.status.value} -> {next_state}",
        )
        return updated.as_dict()

    def remove_service(self, service_id: int) -> dict[str, Any]:
        """Delete a service and clear references from findings."""
        service = self._require_in(self.store.services, service_id, name="service")
        self.store.services.delete(service_id)
        for finding in self.store.findings.where(lambda item: item.service_id == service_id):
            self.store.findings.update(finding.id, {"service_id": 0})
        self._log(
            service.engagement_id, "service", service_id, ActivityAction.DELETED, "Deleted service"
        )
        return service.as_dict()

    def list_services(
        self,
        engagement_id: int,
        *,
        target_id: int = 0,
        asset_id: int = 0,
        status: str = "",
        port: int = 0,
    ) -> list[dict[str, Any]]:
        """List services with filters."""
        self._require_engagement(engagement_id)
        return [
            service.as_dict()
            for service in self.store.services.filter_by_engagement(engagement_id)
            if (not target_id or service.target_id == target_id)
            and (not asset_id or service.asset_id == asset_id)
            and (not status or service.status.value == status)
            and (not port or service.port == port)
        ]

    # ------------------------------------------------------------------
    # Credential use cases
    # ------------------------------------------------------------------

    def add_credential(self, engagement_id: int, data: Mapping[str, Any]) -> dict[str, Any]:
        """Store a credential using a secret reference rather than a raw secret."""
        self._require_engagement(engagement_id)
        report = ValidationReport()
        target_id = require_id(data.get("target_id"), "target_id", report)
        self._raise_if_invalid(report)
        self._require_target(engagement_id, target_id)
        secret_ref = require_text(data.get("secret_ref"), "secret_ref", report)
        if secret_ref and not any(
            marker in secret_ref for marker in ("://", "vault:", "env:", "ref:")
        ):
            report.warn("secret_ref", "Prefer an opaque vault reference over a raw secret")
        username = optional_text(data.get("username"), "username", report)
        rotated_at = validate_iso_date(data.get("rotated_at"), "rotated_at", report)
        notes = optional_text(data.get("notes"), "notes", report)
        self._raise_if_invalid(report)
        credential = self.store.credentials.add(
            Credential(
                engagement_id=engagement_id,
                target_id=target_id,
                username=username,
                secret_ref=secret_ref,
                kind=CredentialKind(str(data.get("kind", CredentialKind.PASSWORD.value))),
                status=CredentialStatus(str(data.get("status", CredentialStatus.CANDIDATE.value))),
                rotated_at=rotated_at,
                notes=notes,
                created_at=now_iso(),
                updated_at=now_iso(),
            )
        )
        self._log(
            engagement_id, "credential", credential.id, ActivityAction.CREATED, "Added credential"
        )
        return credential.safe_dict()

    def update_credential(self, credential_id: int, data: Mapping[str, Any]) -> dict[str, Any]:
        """Apply a partial update to a credential."""
        existing = self._require_in(self.store.credentials, credential_id, name="credential")
        report = ValidationReport()
        changes: dict[str, Any] = {}
        for name in ("username", "secret_ref", "notes"):
            if name in data:
                changes[name] = require_text(data[name], name, report, allow_empty=True)
        if "kind" in data:
            changes["kind"] = CredentialKind(str(data["kind"]))
        if "status" in data:
            changes["status"] = CredentialStatus(str(data["status"]))
        if "target_id" in data:
            changes["target_id"] = require_id(data["target_id"], "target_id", report)
        if "rotated_at" in data:
            changes["rotated_at"] = validate_iso_date(data["rotated_at"], "rotated_at", report)
        self._raise_if_invalid(report)
        if "target_id" in changes:
            self._require_target(existing.engagement_id, changes["target_id"])
        changes["updated_at"] = now_iso()
        updated = self.store.credentials.update(credential_id, changes)
        self._log(
            existing.engagement_id,
            "credential",
            credential_id,
            ActivityAction.UPDATED,
            f"Updated credential fields: {', '.join(sorted(changes))}",
        )
        return updated.safe_dict()

    def rotate_credential(self, credential_id: int, *, secret_ref: str = "") -> dict[str, Any]:
        """Mark a credential as rotated and update its secret reference."""
        credential = self._require_in(self.store.credentials, credential_id, name="credential")
        changes: dict[str, Any] = {"status": CredentialStatus.ROTATED, "rotated_at": now_iso()[:10]}
        if secret_ref:
            changes["secret_ref"] = secret_ref
        updated = self.store.credentials.update(credential_id, changes)
        self._log(
            credential.engagement_id,
            "credential",
            credential_id,
            ActivityAction.UPDATED,
            "Rotated credential",
        )
        return updated.safe_dict()

    def transition_credential(self, credential_id: int, action: str) -> dict[str, Any]:
        """Move a credential through its validation lifecycle."""
        credential = self._require_in(self.store.credentials, credential_id, name="credential")
        try:
            next_state = CREDENTIAL_MACHINE.apply(credential.status.value, action)
        except TransitionError as exc:
            raise EngagementError(
                str(exc),
                code=EngagementErrorCode.TRANSITION,
                status=409,
                details={"action": action, "from": credential.status.value},
            ) from exc
        changes: dict[str, Any] = {"status": CredentialStatus(next_state), "updated_at": now_iso()}
        if next_state == CredentialStatus.ROTATED.value:
            changes["rotated_at"] = now_iso()[:10]
        updated = self.store.credentials.update(credential_id, changes)
        self._log(
            credential.engagement_id,
            "credential",
            credential_id,
            ActivityAction.TRANSITIONED,
            f"{credential.status.value} -> {next_state}",
        )
        return updated.safe_dict()

    def remove_credential(self, credential_id: int) -> dict[str, Any]:
        """Delete a credential."""
        credential = self._require_in(self.store.credentials, credential_id, name="credential")
        self.store.credentials.delete(credential_id)
        self._log(
            credential.engagement_id,
            "credential",
            credential_id,
            ActivityAction.DELETED,
            "Deleted credential",
        )
        return credential.safe_dict()

    def list_credentials(
        self,
        engagement_id: int,
        *,
        target_id: int = 0,
        status: str = "",
        kind: str = "",
    ) -> list[dict[str, Any]]:
        """List credentials with safe secret references."""
        self._require_engagement(engagement_id)
        return [
            credential.safe_dict()
            for credential in self.store.credentials.filter_by_engagement(engagement_id)
            if (not target_id or credential.target_id == target_id)
            and (not status or credential.status.value == status)
            and (not kind or credential.kind.value == kind)
        ]

    # ------------------------------------------------------------------
    # Finding use cases
    # ------------------------------------------------------------------

    def _validate_finding_relations(
        self,
        engagement_id: int,
        target_id: int,
        asset_id: int,
        service_id: int,
    ) -> None:
        if target_id:
            self._require_target(engagement_id, target_id)
        if asset_id:
            asset = self._require_asset(engagement_id, asset_id)
            if target_id and asset.target_id != target_id:
                raise EngagementError(
                    "asset_id belongs to a different target",
                    code=EngagementErrorCode.VALIDATION,
                    details={"field": "asset_id"},
                )
        if service_id:
            service = self._require_service(engagement_id, service_id)
            if target_id and service.target_id != target_id:
                raise EngagementError(
                    "service_id belongs to a different target",
                    code=EngagementErrorCode.VALIDATION,
                    details={"field": "service_id"},
                )

    def create_finding(self, engagement_id: int, data: Mapping[str, Any]) -> dict[str, Any]:
        """Create a finding with severity, CVSS, CWE/CVE, and evidence data."""
        self._require_engagement(engagement_id)
        payload = dict(data)
        vector = validate_cvss_vector(payload.get("cvss_vector"), ValidationReport())
        if vector and "severity" not in payload:
            payload["severity"] = severity_for_score(cvss_base_score(vector)).value
        report = finding_patch_report(payload, partial=False)
        self._raise_if_invalid(report)
        target_id = self._optional_relation(payload, "target_id", report)
        asset_id = self._optional_relation(payload, "asset_id", report)
        service_id = self._optional_relation(payload, "service_id", report)
        duplicate_of = self._optional_relation(payload, "duplicate_of", report)
        self._raise_if_invalid(report)
        self._validate_finding_relations(engagement_id, target_id, asset_id, service_id)
        severity = Severity(str(payload.get("severity", Severity.MEDIUM.value)))
        confidence = Confidence(str(payload.get("confidence", Confidence.MEDIUM.value)))
        status = FindingStatus(str(payload.get("status", FindingStatus.DRAFT.value)))
        if vector and not severity_agreement(severity, vector):
            report.warn("severity", "Declared severity differs from the CVSS band")
        if (
            status is FindingStatus.VERIFIED
            and not str(payload.get("reproduction_steps", "")).strip()
        ):
            report.error("reproduction_steps", "Verified findings require reproduction steps")
        self._raise_if_invalid(report)
        cwe = normalize_cwe(payload.get("cwe"), report)
        cwes = (
            list(payload.get("cwes", [])) if isinstance(payload.get("cwes"), (list, tuple)) else []
        )
        cves = validate_cves(payload.get("cves"), report)
        references = validate_references(payload.get("references"), report)
        tags = validate_tags(payload.get("tags"), report)
        self._raise_if_invalid(report)
        if cwe and cwe not in cwes:
            cwes.insert(0, cwe)
        finding = self.store.findings.add(
            Finding(
                engagement_id=engagement_id,
                target_id=target_id,
                asset_id=asset_id,
                service_id=service_id,
                title=str(payload["title"]).strip(),
                summary=str(payload.get("summary", "")).strip(),
                severity=severity,
                confidence=confidence,
                cvss_vector=vector,
                cvss_score=cvss_base_score(vector) if vector else 0.0,
                cwe=cwe,
                cwes=dedupe(cwes),
                cves=cves,
                status=status,
                duplicate_of=duplicate_of,
                owner=str(payload.get("owner", "")).strip(),
                impact=str(payload.get("impact", "")).strip(),
                remediation=str(payload.get("remediation", "")).strip(),
                reproduction_steps=str(payload.get("reproduction_steps", "")).strip(),
                references=references,
                tags=tags,
                transitions=[
                    FindingEvent(
                        at=now_iso(),
                        actor=self.actor,
                        action="created",
                        to_status=status.value,
                    )
                ],
                created_at=now_iso(),
                updated_at=now_iso(),
            )
        )
        self._log(
            engagement_id,
            "finding",
            finding.id,
            ActivityAction.CREATED,
            f"Added finding {finding.title}",
        )
        return self.finding_detail(finding.id)

    def update_finding(self, finding_id: int, data: Mapping[str, Any]) -> dict[str, Any]:
        """Apply a partial update to a finding."""
        existing = self._require_in(self.store.findings, finding_id, name="finding")
        report = finding_patch_report(data, partial=True)
        self._raise_if_invalid(report)
        changes: dict[str, Any] = {}
        for name in ("title", "summary", "impact", "remediation", "reproduction_steps", "owner"):
            if name in data:
                changes[name] = str(data[name]).strip()
        for name, enum_type in (
            ("severity", Severity),
            ("confidence", Confidence),
            ("status", FindingStatus),
        ):
            if name in data:
                changes[name] = enum_type(str(data[name]))
        if "cvss_vector" in data:
            vector = validate_cvss_vector(data["cvss_vector"], report)
            changes["cvss_vector"] = vector
            changes["cvss_score"] = cvss_base_score(vector) if vector else 0.0
            if vector and "severity" not in data:
                changes["severity"] = severity_for_score(changes["cvss_score"])
        if "cwe" in data:
            changes["cwe"] = normalize_cwe(data["cwe"], report)
            cwes = list(changes.get("cwes", existing.cwes))
            if changes["cwe"] and changes["cwe"] not in cwes:
                cwes.insert(0, changes["cwe"])
            changes["cwes"] = dedupe(cwes)
        if "cwes" in data and isinstance(data["cwes"], (list, tuple)):
            changes["cwes"] = dedupe(
                [normalize_cwe(value, report, name="cwes") for value in data["cwes"]]
            )
        if "cves" in data:
            changes["cves"] = validate_cves(data["cves"], report)
        if "references" in data:
            changes["references"] = validate_references(data["references"], report)
        if "tags" in data:
            changes["tags"] = validate_tags(data["tags"], report)
        for name in ("target_id", "asset_id", "service_id", "duplicate_of"):
            if name in data:
                changes[name] = self._optional_relation(data, name, report)
        self._raise_if_invalid(report)
        self._validate_finding_relations(
            existing.engagement_id,
            changes.get("target_id", existing.target_id),
            changes.get("asset_id", existing.asset_id),
            changes.get("service_id", existing.service_id),
        )
        changes["updated_at"] = now_iso()
        self.store.findings.update(finding_id, changes)
        self._log(
            existing.engagement_id,
            "finding",
            finding_id,
            ActivityAction.UPDATED,
            f"Updated finding fields: {', '.join(sorted(changes))}",
        )
        return self.finding_detail(finding_id)

    def transition_finding(
        self,
        finding_id: int,
        action: str,
        *,
        note: str = "",
        evidence: str = "",
        duplicate_of: int = 0,
        retested: bool = False,
    ) -> dict[str, Any]:
        """Move a finding through its lifecycle with guard checks."""
        finding = self._require_in(self.store.findings, finding_id, name="finding")
        if evidence and not finding.reproduction_steps:
            self.store.findings.update(
                finding_id,
                {"reproduction_steps": evidence, "updated_at": now_iso()},
            )
            finding = self.store.findings.require(finding_id)
        context = transition_context(
            note=note,
            evidence=evidence or finding.reproduction_steps,
            duplicate_of=duplicate_of or finding.duplicate_of,
            retested=retested,
        )
        try:
            next_state = FINDING_MACHINE.apply(finding.status.value, action, context)
        except TransitionError as exc:
            raise EngagementError(
                str(exc),
                code=EngagementErrorCode.TRANSITION,
                status=409,
                details={"action": action, "from": finding.status.value},
            ) from exc
        changes: dict[str, Any] = {
            "status": FindingStatus(next_state),
            "updated_at": now_iso(),
        }
        if action == "mark_duplicate":
            changes["duplicate_of"] = duplicate_of
        if next_state in {FindingStatus.CLOSED.value, FindingStatus.REMEDIATED.value}:
            changes["resolved_at"] = now_iso()
        if next_state in {FindingStatus.OPEN.value, FindingStatus.VERIFIED.value}:
            changes["resolved_at"] = ""
        event = FindingEvent(
            at=now_iso(),
            actor=self.actor,
            action=action,
            from_status=finding.status.value,
            to_status=next_state,
            note=note,
        )
        updated_transitions = [*finding.transitions, event]
        changes["transitions"] = [item.as_dict() for item in updated_transitions]
        self.store.findings.update(finding_id, changes)
        self._log(
            finding.engagement_id,
            "finding",
            finding_id,
            ActivityAction.TRANSITIONED,
            f"{finding.status.value} -> {next_state} ({action})",
        )
        return self.finding_detail(finding_id)

    def mark_finding_duplicate(self, finding_id: int, canonical_id: int) -> dict[str, Any]:
        """Link a finding to a canonical finding and mark it duplicate."""
        finding = self._require_in(self.store.findings, finding_id, name="finding")
        canonical = self._require_in(self.store.findings, canonical_id, name="finding")
        if finding.engagement_id != canonical.engagement_id:
            raise EngagementError(
                "Canonical finding belongs to a different engagement",
                code=EngagementErrorCode.VALIDATION,
                details={"field": "canonical_id"},
            )
        return self.transition_finding(
            finding_id,
            "mark_duplicate",
            duplicate_of=canonical_id,
            note=f"Duplicate of finding {canonical_id}",
        )

    def link_duplicate_cluster(
        self, canonical_id: int, duplicate_ids: Iterable[int]
    ) -> dict[str, Any]:
        """Link multiple findings to a canonical finding."""
        canonical = self._require_in(self.store.findings, canonical_id, name="finding")
        linked: list[dict[str, Any]] = []
        skipped: list[int] = []
        for duplicate_id in duplicate_ids:
            if duplicate_id == canonical_id:
                skipped.append(duplicate_id)
                continue
            try:
                linked.append(self.mark_finding_duplicate(duplicate_id, canonical_id))
            except EngagementError:
                skipped.append(duplicate_id)
        return {
            "canonical_id": canonical.id,
            "linked": linked,
            "skipped": skipped,
            "count": len(linked),
        }

    def remove_finding(self, finding_id: int) -> dict[str, Any]:
        """Delete a finding and clear duplicate links pointing to it."""
        finding = self._require_in(self.store.findings, finding_id, name="finding")
        self.store.findings.delete(finding_id)
        for other in self.store.findings.where(lambda item: item.duplicate_of == finding_id):
            self.store.findings.update(other.id, {"duplicate_of": 0})
        self._log(
            finding.engagement_id, "finding", finding_id, ActivityAction.DELETED, "Deleted finding"
        )
        return finding.as_dict()

    def list_findings(
        self,
        engagement_id: int,
        *,
        status: str = "",
        severity: str = "",
        confidence: str = "",
        target_id: int = 0,
        owner: str = "",
        query: str = "",
        tag: str = "",
    ) -> list[dict[str, Any]]:
        """List findings with filters used by the finding editor table."""
        self._require_engagement(engagement_id)
        needle = query.strip().casefold()
        result: list[dict[str, Any]] = []
        for finding in self.store.findings.filter_by_engagement(engagement_id):
            if status and finding.status.value != status:
                continue
            if severity and finding.severity.value != severity:
                continue
            if confidence and finding.confidence.value != confidence:
                continue
            if target_id and finding.target_id != target_id:
                continue
            if owner and finding.owner.casefold() != owner.casefold():
                continue
            if tag and tag.casefold() not in {value.casefold() for value in finding.tags}:
                continue
            if (
                needle
                and needle
                not in " ".join(
                    [
                        finding.title,
                        finding.summary,
                        finding.impact,
                        finding.remediation,
                        " ".join(finding.cves),
                        finding.cwe,
                    ]
                ).casefold()
            ):
                continue
            result.append(self.finding_detail(finding.id, include_duplicates=False))
        result.sort(
            key=lambda item: (
                -severity_index(Severity(item["severity"])),
                -float(item["cvss_score"]),
                item["id"],
            )
        )
        return result

    def finding_detail(self, finding_id: int, *, include_duplicates: bool = True) -> dict[str, Any]:
        """Return a finding with its CVSS breakdown and duplicate candidates."""
        finding = self._require_in(self.store.findings, finding_id, name="finding")
        data = finding.as_dict()
        data["cvss"] = cvss_breakdown(finding.cvss_vector) if finding.cvss_vector else None
        data["allowed_actions"] = list(
            FINDING_MACHINE.allowed_actions(
                finding.status.value,
                transition_context(duplicate_of=finding.duplicate_of),
            )
        )
        target = self.store.targets.get(finding.target_id) if finding.target_id else None
        data["target_name"] = target.display_name if target else ""
        canonical = self.store.findings.get(finding.duplicate_of) if finding.duplicate_of else None
        data["canonical_title"] = canonical.title if canonical else ""
        if include_duplicates:
            candidates = self.store.findings.filter_by_engagement(finding.engagement_id)
            matches = find_duplicates(finding, candidates)
            data["duplicate_candidates"] = [match.as_dict() for match in matches[:5]]
        else:
            data["duplicate_candidates"] = []
        return data

    def find_duplicates_for(
        self, finding_id: int, *, threshold: float = 0.62
    ) -> list[dict[str, Any]]:
        """Return ranked duplicate candidates for a finding."""
        finding = self._require_in(self.store.findings, finding_id, name="finding")
        candidates = self.store.findings.filter_by_engagement(finding.engagement_id)
        return [
            match.as_dict() for match in find_duplicates(finding, candidates, threshold=threshold)
        ]

    def suggest_duplicate(
        self, finding_id: int, *, threshold: float = 0.62
    ) -> dict[str, Any] | None:
        """Return the strongest duplicate candidate or ``None``."""
        finding = self._require_in(self.store.findings, finding_id, name="finding")
        candidates = self.store.findings.filter_by_engagement(finding.engagement_id)
        match = best_duplicate(finding, candidates, threshold=threshold)
        return match.as_dict() if match else None

    def finding_clusters(
        self, engagement_id: int, *, threshold: float = 0.62
    ) -> list[dict[str, Any]]:
        """Return duplicate clusters for an engagement."""
        self._require_engagement(engagement_id)
        findings = self.store.findings.filter_by_engagement(engagement_id)
        return [
            {
                "ids": [item.id for item in cluster],
                "titles": [item.title for item in cluster],
                "canonical_id": max(cluster, key=lambda item: item.id).id,
            }
            for cluster in cluster_duplicates(findings, threshold=threshold)
            if len(cluster) > 1
        ]

    # ------------------------------------------------------------------
    # Reporting and dashboards
    # ------------------------------------------------------------------

    def coverage_report(self, engagement_id: int) -> dict[str, Any]:
        """Return target coverage with gaps and priorities."""
        self._require_engagement(engagement_id)
        report = compute_coverage(
            engagement_id,
            self.store.targets.filter_by_engagement(engagement_id),
            self.store.assets.filter_by_engagement(engagement_id),
            self.store.services.filter_by_engagement(engagement_id),
            self.store.findings.filter_by_engagement(engagement_id),
        )
        data = report.as_dict()
        data["percent"] = coverage_percent(report)
        data["gap_summary"] = coverage_gap_summary(report)
        data["criticality_distribution"] = criticality_distribution(
            self.store.targets.filter_by_engagement(engagement_id)
        )
        data["out_of_scope_count"] = out_of_scope_count(
            self.store.targets.filter_by_engagement(engagement_id)
        )
        return data

    def dashboard(self, engagement_id: int, *, today: date | None = None) -> dict[str, Any]:
        """Return the complete engagement dashboard payload."""
        engagement = self._require_engagement(engagement_id)
        targets = self.store.targets.filter_by_engagement(engagement_id)
        assets = self.store.assets.filter_by_engagement(engagement_id)
        services = self.store.services.filter_by_engagement(engagement_id)
        credentials = self.store.credentials.filter_by_engagement(engagement_id)
        findings = self.store.findings.filter_by_engagement(engagement_id)
        coverage = self.coverage_report(engagement_id)
        rollup = engagement_rollup(
            engagement,
            targets=targets,
            assets=assets,
            services=services,
            credentials=credentials,
            findings=findings,
            coverage_score=float(coverage["score"]),
            today=today,
        )
        activities = [
            activity.as_dict()
            for activity in self.store.activities.filter_by_engagement(engagement_id)[-10:]
        ]
        return {
            "engagement": self.engagement_detail(engagement_id),
            "rollup": rollup.as_dict(),
            "cards": widget_cards(rollup),
            "coverage": coverage,
            "severity_matrix": severity_matrix(findings),
            "duplicates": duplicate_summary(findings),
            "age_buckets": rollup.age_buckets,
            "recent_activity": list(reversed(activities)),
        }

    def portfolio(self, *, today: date | None = None) -> dict[str, Any]:
        """Return an aggregate portfolio dashboard for all engagements."""
        engagements = self.store.engagements.all()
        rollups = []
        for engagement in engagements:
            coverage = self.coverage_report(engagement.id)
            rollups.append(
                engagement_rollup(
                    engagement,
                    targets=self.store.targets.filter_by_engagement(engagement.id),
                    assets=self.store.assets.filter_by_engagement(engagement.id),
                    services=self.store.services.filter_by_engagement(engagement.id),
                    credentials=self.store.credentials.filter_by_engagement(engagement.id),
                    findings=self.store.findings.filter_by_engagement(engagement.id),
                    coverage_score=float(coverage["score"]),
                    today=today,
                )
            )
        result = portfolio_rollup(engagements, rollups, today=today)
        return result.as_dict()

    def workflows(self) -> list[dict[str, Any]]:
        """Return workflow definitions for schema introspection."""
        return describe_workflows()

    def status_options(self) -> dict[str, list[str]]:
        """Return all enum values used by engagement forms."""
        return {
            "engagement_status": [item.value for item in EngagementStatus],
            "engagement_kind": [item.value for item in EngagementKind],
            "target_kind": [item.value for item in TargetKind],
            "target_status": [item.value for item in TargetStatus],
            "scope_status": [item.value for item in ScopeStatus],
            "asset_kind": [item.value for item in AssetKind],
            "asset_status": [item.value for item in AssetStatus],
            "service_status": [item.value for item in ServiceStatus],
            "credential_kind": [item.value for item in CredentialKind],
            "credential_status": [item.value for item in CredentialStatus],
            "finding_status": [item.value for item in FindingStatus],
            "severity": [item.value for item in Severity],
            "confidence": [item.value for item in CONFIDENCE_ORDER],
            "criticality": [item.value for item in Criticality],
            "scope_rule_kind": [item.value for item in ScopeRuleKind],
            "scope_action": [item.value for item in ScopeAction],
        }

    def activity(self, engagement_id: int, *, limit: int = 50) -> list[dict[str, Any]]:
        """Return recent activity for an engagement."""
        self._require_engagement(engagement_id)
        items = self.store.activities.filter_by_engagement(engagement_id)
        return [item.as_dict() for item in items[-limit:]]

    def seed_demo(self) -> dict[str, Any]:
        """Seed a deterministic demo engagement when the store is empty."""
        if self.store.engagements.count():
            return {"created": False, "engagement": None}
        engagement = seed_demo(self.store)
        return {"created": True, "engagement": engagement.as_dict()}


def build_demo_service() -> EngagementService:
    """Build a service preloaded with one demo engagement."""
    service = EngagementService()
    service.seed_demo()
    return service
