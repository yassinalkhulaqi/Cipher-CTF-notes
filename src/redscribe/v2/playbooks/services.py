"""High-level playbook service shared by API handlers and UI previews."""

from __future__ import annotations

import threading
from typing import Any

from redscribe.v2.playbooks.catalog import PLAYBOOKS
from redscribe.v2.playbooks.dag import ancestors, descendants, validate_dag
from redscribe.v2.playbooks.engine import PlaybookEngine, StepAdvice
from redscribe.v2.playbooks.errors import UnknownStepError, ValidationError
from redscribe.v2.playbooks.import_export import (
    ExportBundle,
    ImportReport,
    build_bundle,
    import_bundle,
    playbook_from_dict,
    run_from_dict,
    snippet_from_dict,
    template_from_dict,
)
from redscribe.v2.playbooks.interpolate import render
from redscribe.v2.playbooks.recommendations import (
    RecommendationContext,
    RecommendationEngine,
)
from redscribe.v2.playbooks.repositories import (
    PlaybookRepository,
    RunRepository,
    SnippetRepository,
    TemplateRepository,
)
from redscribe.v2.playbooks.snippets import (
    SnippetLibrary,
    builtin_snippets,
    compose_snippets,
)
from redscribe.v2.playbooks.state import (
    apply_checklist_state,
    cancel_run,
    mark_step_ready,
    new_run,
    run_progress,
    start_run,
)
from redscribe.v2.playbooks.templates import TemplateEngine, builtin_templates
from redscribe.v2.playbooks.types import (
    ChecklistItem,
    Issue,
    Playbook,
    PlaybookStatus,
    PlaybookStep,
    RunPlan,
    RunState,
    SnippetRecord,
    StepKind,
    StepResult,
    StepStatus,
    TemplateRecord,
    Value,
    Values,
    VariableDefinition,
    VariableKind,
)
from redscribe.v2.playbooks.validation import validate_playbook
from redscribe.v2.playbooks.variables import resolve_variables
from redscribe.v2.playbooks.versions import (
    Version,
    VersionHistory,
    bump_version,
    diff_payloads,
)


class PlaybookService:
    """Owns all playbook state and exposes atomic operations for the API."""

    def __init__(self, *, seed: bool = True) -> None:
        self._lock = threading.RLock()
        self.playbooks = PlaybookRepository()
        self.snippets = SnippetRepository()
        self.templates = TemplateRepository()
        self.runs = RunRepository()
        self.histories: dict[str, VersionHistory] = {}
        self.recent_keys: list[str] = []
        self._snippets = SnippetLibrary()
        self._templates = TemplateEngine()
        self._sync_support()
        if seed:
            self.seed()

    def _sync_support(self) -> None:
        snippet_records = list(self.snippets.items)
        template_records = tuple(self.templates.items)
        self._snippets = SnippetLibrary.from_records(snippet_records)
        self._templates = TemplateEngine(template_records)
        self._engine = PlaybookEngine(self._snippets, self._templates)
        self._recommender = RecommendationEngine(
            tuple(self.playbooks.items), self._snippets, self._templates
        )

    def seed(self) -> None:
        """Load curated playbooks, snippets, and templates."""
        with self._lock:
            for playbook in PLAYBOOKS:
                if not self.playbooks.contains(playbook.key):
                    self.playbooks.put(playbook, validate=False)
                    self._seed_history(playbook.key, playbook.version)
            for record in builtin_snippets():
                if not self.snippets.contains(record.key):
                    self.snippets.put(record, validate=False)
            for template in builtin_templates():
                if not self.templates.contains(template.key):
                    self.templates.put(template, validate=False)
            self._sync_support()

    def reset(self) -> None:
        """Restore the curated catalog and clear all runs."""
        with self._lock:
            self.playbooks.replace_all(list(PLAYBOOKS), validate=False)
            self.snippets.replace_all(list(builtin_snippets()), validate=False)
            self.templates.replace_all(list(builtin_templates()), validate=False)
            self.runs.replace_all([], validate=False)
            self.histories.clear()
            for playbook in PLAYBOOKS:
                self._seed_history(playbook.key, playbook.version)
            self.recent_keys.clear()
            self._sync_support()

    def _seed_history(self, key: str, version: str) -> None:
        self.histories[key] = VersionHistory(key).append(
            version, message="Curated baseline", author="redscribe"
        )

    @property
    def engine(self) -> PlaybookEngine:
        return self._engine

    @property
    def recommender(self) -> RecommendationEngine:
        return self._recommender

    def list_playbooks(
        self,
        *,
        query: str = "",
        tags: tuple[str, ...] = (),
        status: str = "",
        category: str = "",
        limit: int = 50,
    ) -> list[Playbook]:
        """List playbooks with filters and stable ordering."""
        with self._lock:
            needle = query.strip().casefold()
            wanted = {tag.strip().casefold() for tag in tags if tag.strip()}
            results: list[Playbook] = []
            for item in self.playbooks.items:
                if status and item.status.value != status:
                    continue
                if category and item.category.casefold() != category.casefold():
                    continue
                if wanted and not wanted.intersection(item.all_tags()):
                    continue
                haystack = " ".join(
                    (
                        item.key,
                        item.title,
                        item.description,
                        item.category,
                        " ".join(item.tags),
                        " ".join(step.title for step in item.steps),
                    )
                ).casefold()
                if needle and needle not in haystack:
                    continue
                results.append(item)
            return results[:limit]

    def get_playbook(self, key: str) -> Playbook:
        """Return one playbook."""
        with self._lock:
            return self.playbooks.get(key)

    def create_playbook(self, payload: Any) -> Playbook:
        """Create a playbook from an API payload."""
        data = _object(payload, "playbook")
        with self._lock:
            playbook = playbook_from_dict(data).with_changes(
                id=0,
                version=str(data.get("version", "0.1.0")),
            )
            created = self.playbooks.add(playbook, assign_id=True)
            self._seed_history(created.key, created.version)
            self._sync_support()
            return created

    def update_playbook(self, key: str, payload: Any) -> Playbook:
        """Update an existing playbook and append a version entry."""
        data = _object(payload, "playbook")
        with self._lock:
            current = self.playbooks.get(key)
            incoming = playbook_from_dict({**current.as_dict(), **data, "key": current.key})
            bump = str(data.get("bump", "") or "")
            version = str(data.get("version", "") or "")
            if bump:
                version = bump_version(current.version, bump)
            if version and version != current.version:
                if Version.parse(version) <= Version.parse(current.version):
                    version = bump_version(current.version, "patch")
            else:
                version = current.version
            changes = diff_payloads(current.as_dict(), incoming.as_dict())
            if changes and not bump and not data.get("version"):
                version = bump_version(current.version, "minor")
            updated = incoming.with_changes(
                id=current.id,
                key=current.key,
                version=version,
                created_at=current.created_at,
                updated_at=_now(),
            )
            self.playbooks.update(key, updated)
            if changes:
                self.histories[current.key] = self.histories[current.key].append(
                    version,
                    message=str(data.get("message", "Updated playbook")),
                    author=str(data.get("author", "")),
                )
            self._sync_support()
            return updated

    def delete_playbook(self, key: str) -> Playbook:
        """Remove one playbook."""
        with self._lock:
            removed = self.playbooks.remove(key)
            self.histories.pop(removed.key, None)
            self._sync_support()
            return removed

    def clone_playbook(self, key: str, *, new_key: str = "", title: str = "") -> Playbook:
        """Clone a playbook with fresh ids and a new version."""
        with self._lock:
            source = self.playbooks.get(key)
            target = new_key.strip() or f"{source.key}-copy"
            version = bump_version(source.version, "minor")
            clone = source.with_changes(
                id=0,
                key=target,
                title=title.strip() or f"{source.title} (copy)",
                version=version,
                status=PlaybookStatus.DRAFT,
                created_at=_now(),
                updated_at=_now(),
            )
            created = self.playbooks.add(clone, assign_id=True)
            self._seed_history(created.key, version)
            self._sync_support()
            return created

    def validate_playbook(self, key: str) -> tuple[Issue, ...]:
        """Validate one stored playbook."""
        return validate_playbook(self.get_playbook(key))

    def playbook_graph(self, key: str) -> dict[str, Any]:
        """Return DAG metadata for one playbook."""
        playbook = self.get_playbook(key)
        graph = validate_dag(playbook.steps)
        data = graph.as_dict()
        data["playbook_key"] = playbook.key
        data["nodes"] = [step.as_dict() for step in playbook.steps]
        return data

    def step_graph(self, key: str, step_id: str) -> dict[str, Any]:
        """Return the dependency neighborhood of one step."""
        playbook = self.get_playbook(key)
        if not any(step.id == step_id for step in playbook.steps):
            raise UnknownStepError(f"Unknown step: {step_id}")
        graph = {step.id: step.depends_on for step in playbook.steps}
        return {
            "step_id": step_id,
            "ancestors": list(ancestors(graph, step_id)),
            "descendants": list(descendants(graph, step_id)),
        }

    def add_step(self, key: str, payload: Any) -> PlaybookStep:
        """Append one step to a playbook."""
        data = _object(payload, "step")
        with self._lock:
            playbook = self.playbooks.get(key)
            step = _step_from_payload(data)
            if any(item.id == step.id for item in playbook.steps):
                raise ValidationError(f"Duplicate step id: {step.id}")
            updated = playbook.with_changes(steps=(*playbook.steps, step), updated_at=_now())
            self.playbooks.update(key, updated)
            self._sync_support()
            return step

    def update_step(self, key: str, step_id: str, payload: Any) -> PlaybookStep:
        """Replace one step in a playbook."""
        data = _object(payload, "step")
        with self._lock:
            playbook = self.playbooks.get(key)
            steps: list[PlaybookStep] = []
            found = False
            for step in playbook.steps:
                if step.id == step_id:
                    steps.append(_step_from_payload({**step.as_dict(), **data, "id": step_id}))
                    found = True
                else:
                    steps.append(step)
            if not found:
                raise UnknownStepError(f"Unknown step: {step_id}")
            updated = playbook.with_changes(steps=tuple(steps), updated_at=_now())
            self.playbooks.update(key, updated)
            self._sync_support()
            return next(step for step in updated.steps if step.id == step_id)

    def remove_step(self, key: str, step_id: str) -> PlaybookStep:
        """Remove one step and all references to it."""
        with self._lock:
            playbook = self.playbooks.get(key)
            target = next((step for step in playbook.steps if step.id == step_id), None)
            if target is None:
                raise UnknownStepError(f"Unknown step: {step_id}")
            steps = tuple(
                step.with_changes(
                    depends_on=tuple(item for item in step.depends_on if item != step_id)
                )
                for step in playbook.steps
                if step.id != step_id
            )
            self.playbooks.update(key, playbook.with_changes(steps=steps, updated_at=_now()))
            self._sync_support()
            return target

    def move_step(self, key: str, step_id: str, payload: Any) -> PlaybookStep:
        """Move a step to a new position in the ordered step list."""
        data = _object(payload, "move")
        position = int(data.get("position", 0) or 0)
        with self._lock:
            playbook = self.playbooks.get(key)
            steps = list(playbook.steps)
            index = next((i for i, step in enumerate(steps) if step.id == step_id), -1)
            if index < 0:
                raise UnknownStepError(f"Unknown step: {step_id}")
            step = steps.pop(index)
            target = max(0, min(position, len(steps)))
            steps.insert(target, step)
            self.playbooks.update(key, playbook.with_changes(steps=tuple(steps), updated_at=_now()))
            self._sync_support()
            return step

    def link_steps(self, key: str, step_id: str, depends_on: str) -> PlaybookStep:
        """Add a dependency edge."""
        with self._lock:
            playbook = self.playbooks.get(key)
            step = next((item for item in playbook.steps if item.id == step_id), None)
            if step is None:
                raise UnknownStepError(f"Unknown step: {step_id}")
            if not any(item.id == depends_on for item in playbook.steps):
                raise UnknownStepError(f"Unknown dependency: {depends_on}")
            if depends_on in step.depends_on:
                return step
            updated_step = step.with_changes(depends_on=(*step.depends_on, depends_on))
            steps = tuple(updated_step if item.id == step_id else item for item in playbook.steps)
            self.playbooks.update(key, playbook.with_changes(steps=steps, updated_at=_now()))
            self._sync_support()
            return updated_step

    def unlink_steps(self, key: str, step_id: str, depends_on: str) -> PlaybookStep:
        """Remove a dependency edge."""
        with self._lock:
            playbook = self.playbooks.get(key)
            step = next((item for item in playbook.steps if item.id == step_id), None)
            if step is None:
                raise UnknownStepError(f"Unknown step: {step_id}")
            updated_step = step.with_changes(
                depends_on=tuple(item for item in step.depends_on if item != depends_on)
            )
            steps = tuple(updated_step if item.id == step_id else item for item in playbook.steps)
            self.playbooks.update(key, playbook.with_changes(steps=steps, updated_at=_now()))
            self._sync_support()
            return updated_step

    def set_step_checklist(self, key: str, step_id: str, payload: Any) -> PlaybookStep:
        """Replace the checklist attached to one step."""
        data = _object(payload, "checklist")
        items = tuple(
            ChecklistItem(
                id=str(item.get("id", "")),
                label=str(item.get("label", "")),
                detail=str(item.get("detail", "")),
                required=bool(item.get("required", True)),
            )
            for item in _sequence(data.get("items", []))
            if isinstance(item, dict)
        )
        with self._lock:
            playbook = self.playbooks.get(key)
            steps = tuple(
                step.with_changes(checklist=items) if step.id == step_id else step
                for step in playbook.steps
            )
            if all(before is after for before, after in zip(playbook.steps, steps, strict=False)):
                raise UnknownStepError(f"Unknown step: {step_id}")
            self.playbooks.update(key, playbook.with_changes(steps=steps, updated_at=_now()))
            self._sync_support()
            return next(step for step in steps if step.id == step_id)

    def add_variable(self, key: str, payload: Any) -> VariableDefinition:
        """Declare one variable on a playbook."""
        from redscribe.v2.playbooks.import_export import variable_from_dict

        definition = variable_from_dict(payload)
        with self._lock:
            playbook = self.playbooks.get(key)
            if any(item.key == definition.key for item in playbook.variables):
                raise ValidationError(f"Duplicate variable: {definition.key}")
            updated = playbook.with_changes(variables=(*playbook.variables, definition))
            self.playbooks.update(key, updated)
            self._sync_support()
            return definition

    def remove_variable(self, key: str, name: str) -> VariableDefinition:
        """Remove one declared variable."""
        with self._lock:
            playbook = self.playbooks.get(key)
            target = next((item for item in playbook.variables if item.key == name), None)
            if target is None:
                raise ValidationError(f"Unknown variable: {name}")
            variables = tuple(item for item in playbook.variables if item.key != name)
            self.playbooks.update(key, playbook.with_changes(variables=variables))
            self._sync_support()
            return target

    def resolve_variables(self, key: str, payload: Any) -> dict[str, Any]:
        """Resolve variable values for a playbook."""
        data = _object(payload, "variables")
        playbook = self.get_playbook(key)
        result = resolve_variables(
            playbook.variables,
            data.get("values", {}),
            target=str(data.get("target", "")),
            strict=bool(data.get("strict", False)),
        )
        return result.as_dict()

    def list_snippets(
        self,
        *,
        query: str = "",
        tags: tuple[str, ...] = (),
        library: str = "",
        limit: int = 50,
    ) -> list[SnippetRecord]:
        """Search the snippet library."""
        with self._lock:
            return self._snippets.search(query, tags=tags, library=library, limit=limit)

    def get_snippet(self, key: str) -> SnippetRecord:
        """Return one snippet."""
        with self._lock:
            return self.snippets.get(key)

    def create_snippet(self, payload: Any) -> SnippetRecord:
        """Create a snippet record."""
        from redscribe.v2.playbooks.import_export import snippet_from_dict

        data = _object(payload, "snippet")
        with self._lock:
            record = snippet_from_dict(data).with_changes(id=0)
            created = self.snippets.add(record, assign_id=True)
            self._sync_support()
            return created

    def update_snippet(self, key: str, payload: Any) -> SnippetRecord:
        """Update one snippet."""
        from redscribe.v2.playbooks.import_export import snippet_from_dict

        data = _object(payload, "snippet")
        with self._lock:
            current = self.snippets.get(key)
            updated = snippet_from_dict(
                {**current.as_dict(), **data, "key": current.key}
            ).with_changes(id=current.id)
            self.snippets.update(key, updated)
            self._sync_support()
            return updated

    def delete_snippet(self, key: str) -> SnippetRecord:
        """Delete one snippet."""
        with self._lock:
            removed = self.snippets.remove(key)
            self._sync_support()
            return removed

    def use_snippet(self, key: str, *, values: Values | None = None) -> dict[str, Any]:
        """Record usage and render one snippet for copying."""
        with self._lock:
            record = self.snippets.get(key)
            updated = record.with_changes(usage_count=record.usage_count + 1)
            self.snippets.put(updated)
            rendered = render(updated.command, values or {})
            self._sync_support()
            return {
                "snippet": updated.as_dict(),
                "command": rendered.text,
                "warnings": [issue.as_dict() for issue in rendered.issues],
            }

    def compose_snippet_keys(self, keys: list[str], values: Values | None = None) -> dict[str, Any]:
        """Compose several snippets without executing anything."""
        with self._lock:
            records = [self.snippets.get(key) for key in keys]
            return compose_snippets(records, values or {}).as_dict()

    def snippet_stats(self) -> dict[str, Any]:
        """Return snippet library statistics."""
        with self._lock:
            return {
                **self._snippets.stats(),
                "total": len(self.snippets),
            }

    def list_templates(
        self, *, category: str = "", tags: tuple[str, ...] = ()
    ) -> list[TemplateRecord]:
        """List templates with optional filters."""
        with self._lock:
            return self._templates.list_records(category=category, tags=tags)

    def get_template(self, key: str) -> TemplateRecord:
        """Return one template."""
        with self._lock:
            return self.templates.get(key)

    def render_template(
        self,
        key: str,
        values: Values | None = None,
        *,
        target: str = "",
        strict: bool = False,
    ) -> dict[str, Any]:
        """Render one template and return a preview payload."""
        with self._lock:
            return self._templates.render(key, values or {}, strict=strict, target=target).as_dict()

    def template_history(self, key: str) -> dict[str, Any]:
        """Return version history for one template."""
        with self._lock:
            return self._templates.history(key)

    def register_template(self, payload: Any) -> TemplateRecord:
        """Register or update a template."""
        from redscribe.v2.playbooks.import_export import template_from_dict

        data = _object(payload, "template")
        with self._lock:
            record = template_from_dict(data)
            updated = self._templates.register(record)
            self.templates.put(updated, validate=False)
            self._sync_support()
            return updated

    def delete_template(self, key: str) -> TemplateRecord:
        """Delete one template."""
        with self._lock:
            removed = self.templates.remove(key)
            self._sync_support()
            return removed

    def plan_run(self, key: str, payload: Any) -> RunPlan:
        """Create a dry-run plan."""
        data = _object(payload, "run")
        playbook = self.get_playbook(key)
        values: Values = {str(k): _value(v) for k, v in _mapping(data.get("values", {})).items()}
        return self.engine.plan(
            playbook,
            values,
            target=str(data.get("target", "")),
            strict=bool(data.get("strict", False)),
        )

    def preview_run(self, key: str, payload: Any) -> dict[str, Any]:
        """Return a dry-run plan and its Markdown preview."""
        with self._lock:
            plan = self.plan_run(key, payload)
            playbook = self.get_playbook(key)
            return {"plan": plan.as_dict(), "preview": self.engine.preview(playbook, plan)}

    def start_run(self, key: str, payload: Any) -> RunState:
        """Create and start a run."""
        data = _object(payload, "run")
        with self._lock:
            playbook = self.get_playbook(key)
            values: Values = {
                str(k): _value(v) for k, v in _mapping(data.get("values", {})).items()
            }
            run = start_run(new_run(self.runs.next_id(), playbook, values))
            self.runs.put(run, validate=False)
            self._remember(playbook.key)
            if run.current_step == "":
                advice = self.engine.next_step(self.plan_run(key, payload), run)
                if advice is not None:
                    run = mark_step_ready(run, advice.step_id)
                    self.runs.put(run, validate=False)
            return run

    def get_run(self, run_id: int) -> RunState:
        """Return one run by id."""
        with self._lock:
            return self.runs.get(str(run_id))

    def list_runs(self, *, playbook_key: str = "", limit: int = 50) -> list[RunState]:
        """List runs with optional playbook filter."""
        with self._lock:
            items = self.runs.items if not playbook_key else self.runs.by_playbook(playbook_key)
            return sorted(items, key=lambda item: item.id, reverse=True)[:limit]

    def advance_run(self, run_id: int, payload: Any) -> RunState:
        """Apply a step result to a run."""
        data = _object(payload, "result")
        with self._lock:
            run = self.get_run(run_id)
            plan = self.plan_run(run.playbook_key, {"values": run.values})
            result = StepResult(
                status=_step_status(str(data.get("status", "done"))),
                message=str(data.get("message", "")),
                output=str(data.get("output", "")),
                variables={
                    str(k): _value(v) for k, v in _mapping(data.get("variables", {})).items()
                },
            )
            updated = self.engine.advance(
                run, plan, str(data.get("step_id", run.current_step)), result
            )
            self.runs.put(updated, validate=False)
            return updated

    def cancel_run(self, run_id: int, reason: str = "") -> RunState:
        """Cancel one run."""
        with self._lock:
            run = self.get_run(run_id)
            updated = cancel_run(run, reason or "Run cancelled")
            self.runs.put(updated, validate=False)
            return updated

    def next_step(self, run_id: int) -> StepAdvice | None:
        """Return the next step for a run."""
        run = self.get_run(run_id)
        plan = self.plan_run(run.playbook_key, {"values": run.values})
        return self.engine.next_step(plan, run)

    def run_progress(self, run_id: int) -> dict[str, Any]:
        """Return progress for one run."""
        run = self.get_run(run_id)
        return run_progress(run, self.get_playbook(run.playbook_key))

    def set_run_checklist(self, run_id: int, payload: Any) -> RunState:
        """Update one checklist item in a run."""
        data = _object(payload, "checklist")
        with self._lock:
            run = self.get_run(run_id)
            updated = apply_checklist_state(
                run,
                str(data.get("item_id", "")),
                str(data.get("state", "done")),
                note=str(data.get("note", "")),
            )
            self.runs.put(updated, validate=False)
            return updated

    def run_checklist(self, run_id: int) -> dict[str, Any]:
        """Return checklist state for one run."""
        run = self.get_run(run_id)
        playbook = self.get_playbook(run.playbook_key)
        tracker = self.engine.make_tracker(playbook, run)
        return tracker.as_dict()

    def recommend(self, payload: Any) -> list[dict[str, Any]]:
        """Return ranked recommendations for a context."""
        data = _object(payload, "context")
        context = RecommendationContext(
            query=str(data.get("query", "")),
            tags=tuple(str(item) for item in _sequence(data.get("tags", []))),
            target=str(data.get("target", "")),
            category=str(data.get("category", "")),
            recent_keys=tuple(self.recent_keys),
        )
        with self._lock:
            return [item.as_dict() for item in self._recommender.mixed(context)]

    def export(self, *, source: str = "redscribe") -> ExportBundle:
        """Export all playbook data as a portable bundle."""
        with self._lock:
            return build_bundle(
                tuple(self.playbooks.items),
                tuple(self.snippets.items),
                tuple(self.templates.items),
                tuple(self.runs.items),
                source=source,
            )

    def import_bundle(self, payload: Any, *, strategy: str = "skip") -> ImportReport:
        """Import playbook data with duplicate handling."""
        with self._lock:
            present = {
                "playbooks": set(self.playbooks.keys()),
                "snippets": set(self.snippets.keys()),
                "templates": set(self.templates.keys()),
            }
            report = import_bundle(payload, strategy=strategy, existing=present)
            replace_existing = strategy == "replace"
            for playbook in report.playbooks:
                if self.playbooks.contains(playbook.key) and not replace_existing:
                    continue
                self.playbooks.put(playbook, validate=False)
                self._seed_history(playbook.key, playbook.version)
            for snippet in report.snippets:
                if not self.snippets.contains(snippet.key) or replace_existing:
                    self.snippets.put(snippet, validate=False)
            for template in report.templates:
                if not self.templates.contains(template.key) or replace_existing:
                    self.templates.put(template, validate=False)
            for run in report.runs:
                if not self.runs.contains(str(run.id)):
                    self.runs.put(run, validate=False)
            self._sync_support()
            return report

    def stats(self) -> dict[str, Any]:
        """Return service-wide statistics."""
        with self._lock:
            status_counts: dict[str, int] = {}
            for playbook in self.playbooks.items:
                status_counts[playbook.status.value] = (
                    status_counts.get(playbook.status.value, 0) + 1
                )
            return {
                "playbooks": len(self.playbooks),
                "snippets": len(self.snippets),
                "templates": len(self.templates),
                "runs": len(self.runs),
                "steps": sum(len(item.steps) for item in self.playbooks.items),
                "checklist_items": sum(
                    len(step.checklist) for item in self.playbooks.items for step in item.steps
                ),
                "status_counts": status_counts,
                "recent_keys": list(self.recent_keys),
            }

    def options(self) -> dict[str, Any]:
        """Return editor option lists."""
        return {
            "statuses": [item.value for item in PlaybookStatus],
            "step_kinds": [item.value for item in StepKind],
            "step_statuses": [item.value for item in StepStatus],
            "variable_kinds": [item.value for item in VariableKind],
            "categories": sorted({item.category for item in self.playbooks.items}),
            "snippet_libraries": sorted({item.library for item in self.snippets.items}),
        }

    def snapshot(self) -> dict[str, Any]:
        """Serialize all service state."""
        with self._lock:
            return {
                "playbooks": self.playbooks.snapshot(),
                "snippets": self.snippets.snapshot(),
                "templates": self.templates.snapshot(),
                "runs": self.runs.snapshot(),
                "recent_keys": list(self.recent_keys),
            }

    def restore(self, payload: Any) -> None:
        """Restore all service state from a snapshot."""
        data = _object(payload, "snapshot")
        with self._lock:
            self.playbooks.restore(data.get("playbooks", []), playbook_from_dict)
            self.snippets.restore(data.get("snippets", []), snippet_from_dict)
            self.templates.restore(data.get("templates", []), template_from_dict)
            self.runs.restore(data.get("runs", []), run_from_dict)
            self.recent_keys = [str(key) for key in _sequence(data.get("recent_keys", []))]
            self.histories.clear()
            for playbook in self.playbooks.items:
                self._seed_history(playbook.key, playbook.version)
            self._sync_support()

    def _remember(self, key: str) -> None:
        self.recent_keys = [key, *[item for item in self.recent_keys if item != key]][:20]


def _object(payload: Any, label: str) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValidationError(f"Expected {label} payload to be an object")
    return payload


def _sequence(payload: Any) -> list[Any]:
    return list(payload) if isinstance(payload, (list, tuple)) else []


def _mapping(payload: Any) -> dict[str, Any]:
    return dict(payload) if isinstance(payload, dict) else {}


def _value(payload: Any) -> Value:
    from redscribe.v2.playbooks.import_export import value_from_json

    return value_from_json(payload)


def _step_status(value: str) -> StepStatus:
    try:
        return StepStatus(value)
    except ValueError:
        return StepStatus.DONE


def _step_from_payload(data: dict[str, Any]) -> PlaybookStep:
    from redscribe.v2.playbooks.import_export import step_from_dict

    return step_from_dict(data)


def _now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat(timespec="seconds")


__all__ = ["PlaybookService", "StepAdvice"]
