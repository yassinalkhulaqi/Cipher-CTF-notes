"""v4 HTTP handlers for the playbook automation surface.

Handlers return v4 envelopes and never raise across the boundary: validation,
capability and state errors are converted to structured ``ApiError`` payloads.
All actions are data operations — a dry run only produces a trace.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from enum import Enum
from typing import Protocol

from redscribe.v4.api_v4 import Route, RouteRegistry
from redscribe.v4.automation_v4.service import (
    DagValidationError,
    DagValidator,
    DryRunExecutor,
    RunManager,
    RunStateError,
    ScheduleError,
    ScheduleEvaluator,
    ValidationReport,
)
from redscribe.v4.automation_v4.storage import RunStore, StoreError
from redscribe.v4.automation_v4.types import (
    PlaybookDag,
    RunStatus,
    Schedule,
    text,
    text_tuple,
)
from redscribe.v4.capabilities import FeatureFlag, FeatureGate
from redscribe.v4.clock import SYSTEM_CLOCK, Clock
from redscribe.v4.contracts import (
    ApiError,
    Capability,
    CapabilitySet,
    ErrorCode,
    PageMeta,
    fail,
    new_entity_id,
    ok,
)
from redscribe.v4.events import EventBus
from redscribe.v4.pagination import paginate


class Action(str, Enum):
    """Stable action names exposed by the automation API."""

    DESCRIBE = "describe"
    VALIDATE = "validate"
    PLAYBOOKS = "playbooks"
    DRY_RUN = "dry-run"
    RUNS = "runs"
    RUN = "run"
    START = "start"
    COMPLETE = "complete"
    CANCEL = "cancel"
    SCHEDULES = "schedules"
    PLAN_SCHEDULE = "plan-schedule"
    DUE = "due"
    STATS = "stats"

    @classmethod
    def parse(cls, value: str) -> Action:
        normalized = value.strip().casefold()
        for action in cls:
            if action.value == normalized:
                return action
        raise ApiError(ErrorCode.INVALID_INPUT, f"unknown action: {value}")


class PageLike(Protocol):
    """Structural view of a paginated result used for envelope metadata."""

    @property
    def page(self) -> int: ...

    @property
    def page_size(self) -> int: ...

    @property
    def etag(self) -> str: ...

    @property
    def next_cursor(self) -> str: ...


WRITE_ACTIONS = frozenset(
    {
        Action.START,
        Action.COMPLETE,
        Action.CANCEL,
        Action.PLAN_SCHEDULE,
    }
)


@dataclass(frozen=True, slots=True)
class AutomationRequest:
    """A fully decoded, typed request for one automation action."""

    action: Action
    playbook_id: str = ""
    run_id: str = ""
    schedule_id: str = ""
    status: str = ""
    page: int = 1
    page_size: int = 50
    dag: Mapping[str, object] = field(default_factory=dict)
    fail_nodes: tuple[str, ...] = ()
    schedule: Mapping[str, object] = field(default_factory=dict)
    request_id: str = ""

    @classmethod
    def from_payload(
        cls, action: str, payload: Mapping[str, object] | None = None
    ) -> AutomationRequest:
        """Validate and decode an untyped wire payload."""
        payload = payload or {}
        raw_page = payload.get("page", 1)
        raw_size = payload.get("page_size", 50)
        if isinstance(raw_page, bool) or not isinstance(raw_page, int):
            raise ApiError(ErrorCode.INVALID_INPUT, "page must be an integer")
        if isinstance(raw_size, bool) or not isinstance(raw_size, int):
            raise ApiError(ErrorCode.INVALID_INPUT, "page_size must be an integer")
        raw_dag = payload.get("dag", {})
        raw_schedule = payload.get("schedule", {})
        if not isinstance(raw_dag, Mapping):
            raise ApiError(ErrorCode.INVALID_INPUT, "dag must be an object")
        if not isinstance(raw_schedule, Mapping):
            raise ApiError(ErrorCode.INVALID_INPUT, "schedule must be an object")
        return cls(
            action=Action.parse(action),
            playbook_id=text(payload.get("playbook_id")),
            run_id=text(payload.get("run_id")),
            schedule_id=text(payload.get("schedule_id")),
            status=text(payload.get("status")),
            page=raw_page,
            page_size=raw_size,
            dag=dict(raw_dag),
            fail_nodes=text_tuple(payload.get("fail_nodes")),
            schedule=dict(raw_schedule),
            request_id=text(payload.get("request_id")),
        )


def as_api_error(exc: Exception) -> ApiError:
    """Translate domain exceptions into structured API errors."""
    if isinstance(exc, ApiError):
        return exc
    if isinstance(exc, DagValidationError):
        return ApiError(ErrorCode.INVALID_INPUT, str(exc), exc.codes)
    if isinstance(exc, RunStateError):
        code = ErrorCode.NOT_FOUND if str(exc).startswith("unknown run") else ErrorCode.CONFLICT
        return ApiError(code, str(exc))
    if isinstance(exc, StoreError):
        return ApiError(ErrorCode.NOT_FOUND, str(exc))
    if isinstance(exc, ScheduleError):
        return ApiError(ErrorCode.INVALID_INPUT, str(exc))
    if isinstance(exc, (ValueError, TypeError)):
        return ApiError(ErrorCode.INVALID_INPUT, str(exc))
    return ApiError(ErrorCode.INTERNAL, "unexpected automation failure")


class AutomationApi:
    """Action dispatcher producing v4 envelopes for all automation routes."""

    SERVICE_NAME = "playbook-automation"

    def __init__(
        self,
        store: RunStore,
        manager: RunManager,
        executor: DryRunExecutor,
        evaluator: ScheduleEvaluator,
        validator: DagValidator,
        gate: FeatureGate,
        capabilities: CapabilitySet,
        id_factory: Callable[[], str] = new_entity_id,
    ) -> None:
        self.store = store
        self.manager = manager
        self.executor = executor
        self.evaluator = evaluator
        self.validator = validator
        self.gate = gate
        self.capabilities = capabilities
        self.id_factory = id_factory

    def actions(self) -> tuple[str, ...]:
        return tuple(action.value for action in Action)

    def register(self, registry: RouteRegistry) -> tuple[Route, ...]:
        """Register the automation route family on a v4 registry."""
        prefixes = (
            "automation",
            "automation/validate",
            "automation/playbooks",
            "automation/dry-run",
            "automation/runs",
            "automation/schedules",
        )
        return tuple(
            registry.register(prefix, f"{self.SERVICE_NAME}:{prefix}") for prefix in prefixes
        )

    def _meta(self, request: AutomationRequest, page: PageLike | None = None) -> PageMeta:
        return PageMeta(
            request_id=request.request_id or self.id_factory(),
            page=request.page if page is None else page.page,
            page_size=request.page_size if page is None else page.page_size,
            etag="" if page is None else page.etag,
            next_cursor="" if page is None else page.next_cursor,
        )

    def _authorize(self, action: Action) -> None:
        try:
            self.gate.require(FeatureFlag.AUTOMATION)
        except PermissionError as exc:
            raise ApiError(ErrorCode.FORBIDDEN, str(exc)) from exc
        self.capabilities.require(Capability.READ)
        if action in WRITE_ACTIONS:
            self.capabilities.require(Capability.AUTOMATE)
        if action is Action.CANCEL:
            self.capabilities.require(Capability.DELETE)

    def _decode_dag(self, request: AutomationRequest) -> PlaybookDag:
        if request.dag:
            return PlaybookDag.from_dict(request.dag)
        if request.playbook_id:
            return self.store.require_dag(request.playbook_id)
        raise ApiError(ErrorCode.INVALID_INPUT, "dag or playbook_id is required")

    def handle_payload(
        self, action: str, payload: Mapping[str, object] | None = None
    ) -> dict[str, object]:
        """Decode and handle a request, returning an envelope in all cases."""
        try:
            request = AutomationRequest.from_payload(action, payload or {})
            return self.handle(request)
        except Exception as exc:
            return fail(as_api_error(exc))

    def handle(self, request: AutomationRequest) -> dict[str, object]:
        """Dispatch one authorized action to the domain services."""
        try:
            self._authorize(request.action)
            return self._dispatch(request)
        except Exception as exc:
            return fail(as_api_error(exc))

    def _dispatch(self, request: AutomationRequest) -> dict[str, object]:
        action = request.action
        if action is Action.DESCRIBE:
            return ok(
                {
                    "service": self.SERVICE_NAME,
                    "actions": self.actions(),
                    "capabilities": sorted(item.value for item in self.capabilities.granted),
                },
                self._meta(request),
            )
        if action is Action.VALIDATE:
            dag = self._decode_dag(request)
            report = self.executor.validator.validate(dag)
            return ok(self._report_data(report), self._meta(request))
        if action is Action.PLAYBOOKS:
            dags = self.store.all_dags()
            if request.playbook_id:
                dags = tuple(dag for dag in dags if dag.id == request.playbook_id)
            dag_page = paginate(dags, request.page, request.page_size)
            return ok(
                dag_page.to_dict(lambda dag: dag.to_dict()),
                self._meta(request, dag_page),
            )
        if action is Action.DRY_RUN:
            dag = self._decode_dag(request)
            result = self.executor.execute(dag, frozenset(request.fail_nodes))
            return ok(result.to_dict(), self._meta(request))
        if action is Action.RUNS:
            runs = self.manager.list_runs(request.playbook_id, self._status(request.status))
            run_page = paginate(runs, request.page, request.page_size)
            return ok(
                run_page.to_dict(lambda run: run.to_dict()),
                self._meta(request, run_page),
            )
        if action is Action.RUN:
            run = self.manager.get(request.run_id)
            if run is None:
                raise ApiError(ErrorCode.NOT_FOUND, f"unknown run: {request.run_id}")
            return ok(run.to_dict(), self._meta(request))
        if action is Action.START:
            if not request.playbook_id:
                raise ApiError(ErrorCode.INVALID_INPUT, "playbook_id is required")
            run = self.manager.start(request.playbook_id, "api")
            return ok(run.to_dict(), self._meta(request))
        if action is Action.COMPLETE:
            run = self.manager.require(request.run_id)
            dag = self.store.require_dag(run.playbook_id)
            result = self.executor.execute(dag)
            finished = self.manager.finish(request.run_id, result)
            return ok(finished.to_dict(), self._meta(request))
        if action is Action.CANCEL:
            cancelled = self.manager.cancel(request.run_id)
            return ok(cancelled.to_dict(), self._meta(request))
        if action is Action.SCHEDULES:
            if request.playbook_id:
                schedules = self.store.schedules_for(request.playbook_id)
            else:
                schedules = self.store.all_schedules()
            schedule_page = paginate(schedules, request.page, request.page_size)
            return ok(
                schedule_page.to_dict(lambda schedule: schedule.to_dict()),
                self._meta(request, schedule_page),
            )
        if action is Action.PLAN_SCHEDULE:
            if not request.schedule:
                raise ApiError(ErrorCode.INVALID_INPUT, "schedule is required")
            schedule = Schedule.from_dict(
                {**request.schedule, "id": request.schedule_id or text(request.schedule.get("id"))}
            )
            planned = self.manager.plan(schedule)
            return ok(planned.to_dict(), self._meta(request))
        if action is Action.DUE:
            due = self.manager.due_schedules()
            due_page = paginate(due, request.page, request.page_size)
            return ok(
                due_page.to_dict(lambda schedule: schedule.to_dict()),
                self._meta(request, due_page),
            )
        if action is Action.STATS:
            return ok(self.store.stats().to_dict(), self._meta(request))
        raise ApiError(ErrorCode.INVALID_INPUT, f"unhandled action: {action.value}")

    @staticmethod
    def _status(value: str) -> RunStatus | None:
        if not value:
            return None
        try:
            return RunStatus.parse(value)
        except ValueError as exc:
            raise ApiError(ErrorCode.INVALID_INPUT, str(exc)) from exc

    @staticmethod
    def _report_data(report: ValidationReport) -> dict[str, object]:
        return report.to_dict()


def build_api(
    store: RunStore | None = None,
    gate: FeatureGate | None = None,
    capabilities: CapabilitySet | None = None,
    clock: Clock | None = None,
) -> AutomationApi:
    """Construct the automation API with injectable foundation services."""
    active_clock = clock or SYSTEM_CLOCK
    active_store = store or RunStore()
    executor = DryRunExecutor()
    evaluator = ScheduleEvaluator(active_clock)
    bus = EventBus()
    manager = RunManager(active_store, bus, executor, evaluator, active_clock)
    return AutomationApi(
        store=active_store,
        manager=manager,
        executor=executor,
        evaluator=evaluator,
        validator=executor.validator,
        gate=gate or FeatureGate(CapabilitySet.full()),
        capabilities=capabilities or CapabilitySet.full(),
    )


def register(api: AutomationApi, registry: RouteRegistry | None = None) -> tuple[Route, ...]:
    """Register automation routes, creating the process registry by default."""
    from redscribe.v4.api_v4 import global_registry

    return api.register(registry or global_registry())


__all__ = [
    "WRITE_ACTIONS",
    "Action",
    "AutomationApi",
    "AutomationRequest",
    "as_api_error",
    "build_api",
    "register",
]
