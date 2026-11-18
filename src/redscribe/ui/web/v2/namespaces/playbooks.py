"""Additive v2 API namespace for playbooks, snippets, and templates.

The namespace registers on an existing :class:`ApiV2` registry through its
``_register`` hook. Shared route tables, transport, and storage modules are
left unchanged, so v1 behavior and the platform kernel remain untouched.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Any

from redscribe.ui.web.v2.contracts import (
    MAX_PAGE_SIZE,
    V2Error,
    V2ErrorCode,
    compute_etag,
    optional_int,
    optional_str,
    paginate,
    require_int,
    require_str,
)
from redscribe.ui.web.v2.routes import RouteResult
from redscribe.v2.playbooks.errors import PlaybookError
from redscribe.v2.playbooks.services import PlaybookService
from redscribe.v2.playbooks.types import Values

Handler = Callable[[dict[str, Any]], RouteResult]

DEFAULT_LIMIT = 50

_ERROR_CODES = {
    "validation_failed": V2ErrorCode.INVALID_REQUEST.value,
    "not_found": V2ErrorCode.NOT_FOUND.value,
    "duplicate_key": V2ErrorCode.CONFLICT.value,
    "invalid_state": V2ErrorCode.CONFLICT.value,
    "cycle_detected": V2ErrorCode.INVALID_REQUEST.value,
    "missing_variable": V2ErrorCode.INVALID_REQUEST.value,
    "unknown_step": V2ErrorCode.NOT_FOUND.value,
    "unknown_snippet": V2ErrorCode.NOT_FOUND.value,
    "unknown_template": V2ErrorCode.NOT_FOUND.value,
    "import_failed": V2ErrorCode.INVALID_REQUEST.value,
    "version_conflict": V2ErrorCode.CONFLICT.value,
    "expression_error": V2ErrorCode.INVALID_REQUEST.value,
    "interpolation_error": V2ErrorCode.INVALID_REQUEST.value,
    "repository_error": V2ErrorCode.INVALID_REQUEST.value,
}


class RouteSpec:
    """Declarative metadata for one playbook namespace route."""

    __slots__ = (
        "description",
        "entity_type",
        "handler",
        "mutating",
        "name",
        "optional",
        "required",
    )

    def __init__(
        self,
        name: str,
        handler: Handler,
        description: str,
        *,
        required: tuple[str, ...] = (),
        optional: tuple[str, ...] = (),
        mutating: bool = False,
        entity_type: str = "",
    ) -> None:
        self.name = name
        self.handler = handler
        self.description = description
        self.required = required
        self.optional = optional
        self.mutating = mutating
        self.entity_type = entity_type


def _to_v2_error(error: PlaybookError) -> V2Error:
    code = error.code.value
    return V2Error(
        error.status,
        _ERROR_CODES.get(code, V2ErrorCode.INVALID_REQUEST.value),
        error.message,
        details=error.details,
    )


def _page_limit(body: Mapping[str, Any]) -> int:
    limit = optional_int(body, "limit")
    if limit is None:
        return DEFAULT_LIMIT
    if limit < 1 or limit > MAX_PAGE_SIZE:
        raise V2Error(
            400,
            V2ErrorCode.INVALID_REQUEST,
            f"limit must be between 1 and {MAX_PAGE_SIZE}",
            details={"field": "limit"},
        )
    return limit


def _tags(body: Mapping[str, Any], key: str = "tags") -> tuple[str, ...]:
    value = body.get(key)
    if isinstance(value, str):
        return tuple(part.strip() for part in value.split(",") if part.strip())
    if isinstance(value, list):
        return tuple(str(part).strip() for part in value if str(part).strip())
    return ()


def _values(body: Mapping[str, Any]) -> Values:
    raw = body.get("values")
    if not isinstance(raw, dict):
        return {}
    result: Values = {}
    for key, value in raw.items():
        name = str(key).strip()
        if not name:
            continue
        if isinstance(value, (str, int, float, bool)):
            result[name] = value
        elif isinstance(value, list):
            result[name] = tuple(str(item) for item in value)
    return result


def _list_result(body: Mapping[str, Any], items: Sequence[Any]) -> RouteResult:
    page_items, page = paginate(
        list(items), cursor=optional_str(body, "cursor"), limit=_page_limit(body)
    )
    etag = compute_etag({"items": page_items, "page": page.as_dict()})
    return RouteResult(list(page_items), page=page, etag=etag)


def _detail_result(data: Mapping[str, Any], *, status: int = 200) -> RouteResult:
    value = dict(data)
    return RouteResult(value, etag=compute_etag(value), status=status)


def _guarded(handler: Handler) -> Handler:
    def wrapped(body: dict[str, Any]) -> RouteResult:
        try:
            return handler(body)
        except PlaybookError as exc:
            raise _to_v2_error(exc) from exc
        except (ValueError, TypeError) as exc:
            raise V2Error(400, V2ErrorCode.INVALID_REQUEST, str(exc)) from exc

    return wrapped


class PlaybooksNamespace:
    """Route handlers bound to one playbook service instance."""

    def __init__(self, service: PlaybookService | None = None) -> None:
        self.service = service if service is not None else PlaybookService()

    def register(self, api: object) -> None:
        """Register every namespace route on a v2 API registry."""
        registrar = getattr(api, "_register", None)
        if not callable(registrar):
            raise TypeError("API registry does not expose a route registration hook")
        for spec in self.specs():
            registrar(
                spec.name,
                _guarded(spec.handler),
                spec.description,
                required=spec.required,
                optional=spec.optional,
                mutating=spec.mutating,
                entity_type=spec.entity_type,
            )

    def specs(self) -> tuple[RouteSpec, ...]:
        """Return the full namespace route inventory."""
        return (
            RouteSpec(
                "playbooks.list",
                self.playbooks_list,
                "List playbooks with query, tag, status, and category filters.",
                optional=("query", "tags", "status", "category", "cursor", "limit"),
            ),
            RouteSpec(
                "playbooks.get",
                self.playbooks_get,
                "Return one playbook with all steps and variables.",
                required=("key",),
            ),
            RouteSpec(
                "playbooks.create",
                self.playbooks_create,
                "Create a playbook from a structured payload.",
                required=("key", "title"),
                optional=(
                    "description",
                    "status",
                    "category",
                    "tags",
                    "version",
                    "steps",
                    "variables",
                ),
                mutating=True,
                entity_type="playbook",
            ),
            RouteSpec(
                "playbooks.update",
                self.playbooks_update,
                "Update a playbook and record a version entry.",
                required=("key",),
                optional=(
                    "title",
                    "description",
                    "status",
                    "category",
                    "tags",
                    "steps",
                    "variables",
                    "bump",
                    "message",
                ),
                mutating=True,
                entity_type="playbook",
            ),
            RouteSpec(
                "playbooks.delete",
                self.playbooks_delete,
                "Delete one playbook.",
                required=("key",),
                mutating=True,
                entity_type="playbook",
            ),
            RouteSpec(
                "playbooks.clone",
                self.playbooks_clone,
                "Clone a playbook as a new draft.",
                required=("key",),
                optional=("new_key", "title"),
                mutating=True,
                entity_type="playbook",
            ),
            RouteSpec(
                "playbooks.validate",
                self.playbooks_validate,
                "Validate a stored playbook and return all issues.",
                required=("key",),
            ),
            RouteSpec(
                "playbooks.graph",
                self.playbooks_graph,
                "Return DAG order, layers, cycles, and critical path.",
                required=("key",),
            ),
            RouteSpec(
                "playbooks.step_graph",
                self.playbooks_step_graph,
                "Return ancestors and descendants of one step.",
                required=("key", "step_id"),
            ),
            RouteSpec(
                "playbooks.recommend",
                self.playbooks_recommend,
                "Recommend playbooks, snippets, and templates for a context.",
                optional=("query", "tags", "target", "category"),
            ),
            RouteSpec(
                "playbooks.stats",
                self.playbooks_stats,
                "Return playbook, step, checklist, and run statistics.",
            ),
            RouteSpec(
                "playbooks.options",
                self.playbooks_options,
                "Return enum values and editor options.",
            ),
            RouteSpec(
                "playbooks.export",
                self.playbooks_export,
                "Export a checksummed playbook bundle.",
                optional=("source",),
            ),
            RouteSpec(
                "playbooks.import",
                self.playbooks_import,
                "Import a playbook bundle with duplicate handling.",
                required=("bundle",),
                optional=("strategy",),
                mutating=True,
                entity_type="playbook",
            ),
            RouteSpec(
                "playbooks.reset",
                self.playbooks_reset,
                "Restore the curated catalog and clear runs.",
                mutating=True,
                entity_type="playbook",
            ),
            RouteSpec(
                "steps.add",
                self.steps_add,
                "Add one step to a playbook.",
                required=("key", "step"),
                mutating=True,
                entity_type="step",
            ),
            RouteSpec(
                "steps.update",
                self.steps_update,
                "Update one playbook step.",
                required=("key", "step_id", "step"),
                mutating=True,
                entity_type="step",
            ),
            RouteSpec(
                "steps.remove",
                self.steps_remove,
                "Remove one step and its dependency edges.",
                required=("key", "step_id"),
                mutating=True,
                entity_type="step",
            ),
            RouteSpec(
                "steps.move",
                self.steps_move,
                "Move one step to a new position.",
                required=("key", "step_id", "position"),
                mutating=True,
                entity_type="step",
            ),
            RouteSpec(
                "steps.link",
                self.steps_link,
                "Add a dependency from one step to another.",
                required=("key", "step_id", "depends_on"),
                mutating=True,
                entity_type="step",
            ),
            RouteSpec(
                "steps.unlink",
                self.steps_unlink,
                "Remove a dependency edge.",
                required=("key", "step_id", "depends_on"),
                mutating=True,
                entity_type="step",
            ),
            RouteSpec(
                "steps.checklist",
                self.steps_checklist,
                "Replace the checklist attached to one step.",
                required=("key", "step_id", "items"),
                mutating=True,
                entity_type="step",
            ),
            RouteSpec(
                "variables.add",
                self.variables_add,
                "Declare one variable on a playbook.",
                required=("key", "variable"),
                mutating=True,
                entity_type="variable",
            ),
            RouteSpec(
                "variables.remove",
                self.variables_remove,
                "Remove one declared variable.",
                required=("key", "name"),
                mutating=True,
                entity_type="variable",
            ),
            RouteSpec(
                "variables.resolve",
                self.variables_resolve,
                "Resolve and validate variable values.",
                required=("key",),
                optional=("values", "target", "strict"),
            ),
            RouteSpec(
                "snippets.list",
                self.snippets_list,
                "Search snippets by query, tags, and library.",
                optional=("query", "tags", "library", "cursor", "limit"),
            ),
            RouteSpec(
                "snippets.get",
                self.snippets_get,
                "Return one snippet record.",
                required=("key",),
            ),
            RouteSpec(
                "snippets.create",
                self.snippets_create,
                "Create a snippet in the personal library.",
                required=("key", "title", "command"),
                optional=("description", "tags", "library"),
                mutating=True,
                entity_type="snippet",
            ),
            RouteSpec(
                "snippets.update",
                self.snippets_update,
                "Update one snippet.",
                required=("key",),
                optional=("title", "command", "description", "tags", "library"),
                mutating=True,
                entity_type="snippet",
            ),
            RouteSpec(
                "snippets.delete",
                self.snippets_delete,
                "Delete one snippet.",
                required=("key",),
                mutating=True,
                entity_type="snippet",
            ),
            RouteSpec(
                "snippets.use",
                self.snippets_use,
                "Render a snippet for copying and record usage.",
                required=("key",),
                optional=("values",),
                mutating=True,
                entity_type="snippet",
            ),
            RouteSpec(
                "snippets.compose",
                self.snippets_compose,
                "Compose several snippets and resolve variables.",
                required=("keys",),
                optional=("values",),
            ),
            RouteSpec(
                "snippets.stats",
                self.snippets_stats,
                "Return snippet library statistics.",
            ),
            RouteSpec(
                "templates.list",
                self.templates_list,
                "List templates with category and tag filters.",
                optional=("category", "tags", "cursor", "limit"),
            ),
            RouteSpec(
                "templates.get",
                self.templates_get,
                "Return one template with its variables.",
                required=("key",),
            ),
            RouteSpec(
                "templates.render",
                self.templates_render,
                "Render a template preview with variables.",
                required=("key",),
                optional=("values", "target", "strict"),
            ),
            RouteSpec(
                "templates.history",
                self.templates_history,
                "Return template version history.",
                required=("key",),
            ),
            RouteSpec(
                "templates.register",
                self.templates_register,
                "Register or update a custom template.",
                required=("key", "name", "content"),
                optional=("description", "tags", "category", "version", "variables"),
                mutating=True,
                entity_type="template",
            ),
            RouteSpec(
                "templates.delete",
                self.templates_delete,
                "Delete one custom template.",
                required=("key",),
                mutating=True,
                entity_type="template",
            ),
            RouteSpec(
                "runs.plan",
                self.runs_plan,
                "Create a dry-run plan with interpolated commands.",
                required=("key",),
                optional=("values", "target", "strict"),
            ),
            RouteSpec(
                "runs.preview",
                self.runs_preview,
                "Return a dry-run plan and Markdown preview.",
                required=("key",),
                optional=("values", "target", "strict"),
            ),
            RouteSpec(
                "runs.start",
                self.runs_start,
                "Start a new playbook run.",
                required=("key",),
                optional=("values", "target", "strict"),
                mutating=True,
                entity_type="run",
            ),
            RouteSpec(
                "runs.get",
                self.runs_get,
                "Return one run with its event history.",
                required=("id",),
            ),
            RouteSpec(
                "runs.list",
                self.runs_list,
                "List runs with an optional playbook filter.",
                optional=("playbook_key", "cursor", "limit"),
            ),
            RouteSpec(
                "runs.next",
                self.runs_next,
                "Return the next executable step for a run.",
                required=("id",),
            ),
            RouteSpec(
                "runs.advance",
                self.runs_advance,
                "Record a step result and advance the run.",
                required=("id", "step_id"),
                optional=("status", "message", "output", "variables"),
                mutating=True,
                entity_type="run",
            ),
            RouteSpec(
                "runs.cancel",
                self.runs_cancel,
                "Cancel one run.",
                required=("id",),
                optional=("reason",),
                mutating=True,
                entity_type="run",
            ),
            RouteSpec(
                "runs.progress",
                self.runs_progress,
                "Return step and checklist progress for a run.",
                required=("id",),
            ),
            RouteSpec(
                "runs.checklist",
                self.runs_checklist,
                "Return checklist state for a run.",
                required=("id",),
            ),
            RouteSpec(
                "runs.set_checklist",
                self.runs_set_checklist,
                "Update one checklist item in a run.",
                required=("id", "item_id", "state"),
                optional=("note",),
                mutating=True,
                entity_type="run",
            ),
        )

    def playbooks_list(self, body: dict[str, Any]) -> RouteResult:
        items = self.service.list_playbooks(
            query=optional_str(body, "query") or "",
            tags=_tags(body),
            status=optional_str(body, "status") or "",
            category=optional_str(body, "category") or "",
            limit=_page_limit(body),
        )
        return _list_result(body, [item.as_dict(include_steps=False) for item in items])

    def playbooks_get(self, body: dict[str, Any]) -> RouteResult:
        return _detail_result(self.service.get_playbook(require_str(body, "key")).as_dict())

    def playbooks_create(self, body: dict[str, Any]) -> RouteResult:
        created = self.service.create_playbook(body)
        return _detail_result(created.as_dict(), status=201)

    def playbooks_update(self, body: dict[str, Any]) -> RouteResult:
        return _detail_result(
            self.service.update_playbook(require_str(body, "key"), body).as_dict()
        )

    def playbooks_delete(self, body: dict[str, Any]) -> RouteResult:
        return _detail_result(
            self.service.delete_playbook(require_str(body, "key")).as_dict(include_steps=False)
        )

    def playbooks_clone(self, body: dict[str, Any]) -> RouteResult:
        clone = self.service.clone_playbook(
            require_str(body, "key"),
            new_key=optional_str(body, "new_key") or "",
            title=optional_str(body, "title") or "",
        )
        return _detail_result(clone.as_dict(), status=201)

    def playbooks_validate(self, body: dict[str, Any]) -> RouteResult:
        key = require_str(body, "key")
        issues = self.service.validate_playbook(key)
        return _detail_result(
            {
                "key": key,
                "ok": not any(issue.is_error for issue in issues),
                "issues": [issue.as_dict() for issue in issues],
            }
        )

    def playbooks_graph(self, body: dict[str, Any]) -> RouteResult:
        return _detail_result(self.service.playbook_graph(require_str(body, "key")))

    def playbooks_step_graph(self, body: dict[str, Any]) -> RouteResult:
        return _detail_result(
            self.service.step_graph(require_str(body, "key"), require_str(body, "step_id"))
        )

    def playbooks_recommend(self, body: dict[str, Any]) -> RouteResult:
        return _detail_result({"recommendations": self.service.recommend(body)})

    def playbooks_stats(self, body: dict[str, Any]) -> RouteResult:
        del body
        return _detail_result(self.service.stats())

    def playbooks_options(self, body: dict[str, Any]) -> RouteResult:
        del body
        return _detail_result(self.service.options())

    def playbooks_export(self, body: dict[str, Any]) -> RouteResult:
        return _detail_result(
            self.service.export(source=optional_str(body, "source") or "redscribe").as_dict()
        )

    def playbooks_import(self, body: dict[str, Any]) -> RouteResult:
        bundle = body.get("bundle")
        if bundle is None:
            raise V2Error(
                400, V2ErrorCode.MISSING_FIELD, "Missing 'bundle'", details={"field": "bundle"}
            )
        strategy = optional_str(body, "strategy") or "skip"
        if strategy not in ("skip", "replace", "rename"):
            raise V2Error(
                400,
                V2ErrorCode.INVALID_CHOICE,
                "strategy must be skip, replace, or rename",
                details={"field": "strategy"},
            )
        return _detail_result(self.service.import_bundle(bundle, strategy=strategy).as_dict())

    def playbooks_reset(self, body: dict[str, Any]) -> RouteResult:
        del body
        self.service.reset()
        return _detail_result(self.service.stats())

    def steps_add(self, body: dict[str, Any]) -> RouteResult:
        step = self.service.add_step(require_str(body, "key"), body.get("step"))
        return _detail_result(step.as_dict(), status=201)

    def steps_update(self, body: dict[str, Any]) -> RouteResult:
        step = self.service.update_step(
            require_str(body, "key"), require_str(body, "step_id"), body.get("step")
        )
        return _detail_result(step.as_dict())

    def steps_remove(self, body: dict[str, Any]) -> RouteResult:
        return _detail_result(
            self.service.remove_step(
                require_str(body, "key"), require_str(body, "step_id")
            ).as_dict()
        )

    def steps_move(self, body: dict[str, Any]) -> RouteResult:
        return _detail_result(
            self.service.move_step(
                require_str(body, "key"),
                require_str(body, "step_id"),
                {"position": require_int(body, "position")},
            ).as_dict()
        )

    def steps_link(self, body: dict[str, Any]) -> RouteResult:
        return _detail_result(
            self.service.link_steps(
                require_str(body, "key"),
                require_str(body, "step_id"),
                require_str(body, "depends_on"),
            ).as_dict()
        )

    def steps_unlink(self, body: dict[str, Any]) -> RouteResult:
        return _detail_result(
            self.service.unlink_steps(
                require_str(body, "key"),
                require_str(body, "step_id"),
                require_str(body, "depends_on"),
            ).as_dict()
        )

    def steps_checklist(self, body: dict[str, Any]) -> RouteResult:
        return _detail_result(
            self.service.set_step_checklist(
                require_str(body, "key"),
                require_str(body, "step_id"),
                {"items": body.get("items", [])},
            ).as_dict()
        )

    def variables_add(self, body: dict[str, Any]) -> RouteResult:
        definition = self.service.add_variable(require_str(body, "key"), body.get("variable"))
        return _detail_result(definition.as_dict(), status=201)

    def variables_remove(self, body: dict[str, Any]) -> RouteResult:
        return _detail_result(
            self.service.remove_variable(
                require_str(body, "key"), require_str(body, "name")
            ).as_dict()
        )

    def variables_resolve(self, body: dict[str, Any]) -> RouteResult:
        return _detail_result(self.service.resolve_variables(require_str(body, "key"), body))

    def snippets_list(self, body: dict[str, Any]) -> RouteResult:
        items = self.service.list_snippets(
            query=optional_str(body, "query") or "",
            tags=_tags(body),
            library=optional_str(body, "library") or "",
            limit=_page_limit(body),
        )
        return _list_result(body, [item.as_dict() for item in items])

    def snippets_get(self, body: dict[str, Any]) -> RouteResult:
        return _detail_result(self.service.get_snippet(require_str(body, "key")).as_dict())

    def snippets_create(self, body: dict[str, Any]) -> RouteResult:
        return _detail_result(self.service.create_snippet(body).as_dict(), status=201)

    def snippets_update(self, body: dict[str, Any]) -> RouteResult:
        return _detail_result(self.service.update_snippet(require_str(body, "key"), body).as_dict())

    def snippets_delete(self, body: dict[str, Any]) -> RouteResult:
        return _detail_result(self.service.delete_snippet(require_str(body, "key")).as_dict())

    def snippets_use(self, body: dict[str, Any]) -> RouteResult:
        return _detail_result(
            self.service.use_snippet(require_str(body, "key"), values=_values(body))
        )

    def snippets_compose(self, body: dict[str, Any]) -> RouteResult:
        keys = body.get("keys")
        if not isinstance(keys, list) or not all(isinstance(key, str) for key in keys):
            raise V2Error(
                400,
                V2ErrorCode.INVALID_TYPE,
                "'keys' must be a list of strings",
                details={"field": "keys"},
            )
        return _detail_result(self.service.compose_snippet_keys(keys, _values(body)))

    def snippets_stats(self, body: dict[str, Any]) -> RouteResult:
        del body
        return _detail_result(self.service.snippet_stats())

    def templates_list(self, body: dict[str, Any]) -> RouteResult:
        items = self.service.list_templates(
            category=optional_str(body, "category") or "", tags=_tags(body)
        )
        return _list_result(body, [item.as_dict(include_content=False) for item in items])

    def templates_get(self, body: dict[str, Any]) -> RouteResult:
        return _detail_result(self.service.get_template(require_str(body, "key")).as_dict())

    def templates_render(self, body: dict[str, Any]) -> RouteResult:
        return _detail_result(
            self.service.render_template(
                require_str(body, "key"),
                _values(body),
                target=optional_str(body, "target") or "",
                strict=bool(body.get("strict", False)),
            )
        )

    def templates_history(self, body: dict[str, Any]) -> RouteResult:
        return _detail_result(self.service.template_history(require_str(body, "key")))

    def templates_register(self, body: dict[str, Any]) -> RouteResult:
        return _detail_result(self.service.register_template(body).as_dict(), status=201)

    def templates_delete(self, body: dict[str, Any]) -> RouteResult:
        return _detail_result(self.service.delete_template(require_str(body, "key")).as_dict())

    def runs_plan(self, body: dict[str, Any]) -> RouteResult:
        return _detail_result(self.service.plan_run(require_str(body, "key"), body).as_dict())

    def runs_preview(self, body: dict[str, Any]) -> RouteResult:
        return _detail_result(self.service.preview_run(require_str(body, "key"), body))

    def runs_start(self, body: dict[str, Any]) -> RouteResult:
        return _detail_result(
            self.service.start_run(require_str(body, "key"), body).as_dict(), status=201
        )

    def runs_get(self, body: dict[str, Any]) -> RouteResult:
        return _detail_result(self.service.get_run(require_int(body, "id")).as_dict())

    def runs_list(self, body: dict[str, Any]) -> RouteResult:
        items = self.service.list_runs(playbook_key=optional_str(body, "playbook_key") or "")
        return _list_result(body, [item.as_dict(include_events=False) for item in items])

    def runs_next(self, body: dict[str, Any]) -> RouteResult:
        advice = self.service.next_step(require_int(body, "id"))
        return _detail_result(advice.as_dict() if advice is not None else {"step_id": ""})

    def runs_advance(self, body: dict[str, Any]) -> RouteResult:
        return _detail_result(self.service.advance_run(require_int(body, "id"), body).as_dict())

    def runs_cancel(self, body: dict[str, Any]) -> RouteResult:
        return _detail_result(
            self.service.cancel_run(
                require_int(body, "id"), optional_str(body, "reason") or ""
            ).as_dict()
        )

    def runs_progress(self, body: dict[str, Any]) -> RouteResult:
        return _detail_result(self.service.run_progress(require_int(body, "id")))

    def runs_checklist(self, body: dict[str, Any]) -> RouteResult:
        return _detail_result(self.service.run_checklist(require_int(body, "id")))

    def runs_set_checklist(self, body: dict[str, Any]) -> RouteResult:
        return _detail_result(
            self.service.set_run_checklist(require_int(body, "id"), body).as_dict()
        )


_active_namespace = PlaybooksNamespace()


def configure(service: PlaybookService | None = None) -> PlaybooksNamespace:
    """Configure the process-wide namespace used by bare ``register(api)``."""
    global _active_namespace
    _active_namespace = PlaybooksNamespace(service)
    return _active_namespace


def register(api: object, service: PlaybookService | None = None) -> PlaybooksNamespace:
    """Register playbook routes on a v2 API registry."""
    namespace = PlaybooksNamespace(service) if service is not None else _active_namespace
    try:
        namespace.register(api)
    except PlaybookError as exc:
        raise _to_v2_error(exc) from exc
    return namespace


def route_names() -> tuple[str, ...]:
    """Return all playbook route names without creating a service."""
    return tuple(spec.name for spec in _active_namespace.specs())


__all__ = [
    "PlaybooksNamespace",
    "RouteSpec",
    "configure",
    "register",
    "route_names",
]
