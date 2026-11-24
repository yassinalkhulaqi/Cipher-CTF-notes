"""Application service orchestrating the command center."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from redscribe.v3.capabilities import Capabilities
from redscribe.v3.clock import Clock, SystemClock
from redscribe.v3.commands.capabilities import (
    CommandCapabilityGuard,
    CommandDeniedError,
    CommandPolicy,
)
from redscribe.v3.commands.context import ContextResolver
from redscribe.v3.commands.focus import FocusSession, FocusSessionManager
from redscribe.v3.commands.macros import (
    Macro,
    MacroError,
    MacroLibrary,
    MacroRecorder,
    expand_macro,
)
from redscribe.v3.commands.navigation import (
    NavigationGraph,
    NavNode,
    default_navigation,
)
from redscribe.v3.commands.parser import BindingError
from redscribe.v3.commands.registry import CommandRegistry, default_registry
from redscribe.v3.commands.scoring import group_hits, rank_commands
from redscribe.v3.commands.types import (
    CommandContext,
    CommandDenial,
    CommandEffect,
    CommandGroupResult,
    CommandInvocation,
    CommandResult,
    CommandSpec,
    DenialReason,
    PermissionLevel,
)
from redscribe.v3.commands.usage import UsageModel
from redscribe.v3.commands.workspace import WorkspaceManager, default_workspace
from redscribe.v3.entities.ids import try_parse
from redscribe.v3.entities.types import EntityRef
from redscribe.v3.events import EventBus, make_event

EXECUTED_EVENT = "command.executed"
MACRO_EVENT = "command.macro_saved"
FOCUS_EVENT = "command.focus_changed"
WORKSPACE_EVENT = "command.workspace_changed"


@dataclass(slots=True)
class CommandCenterService:
    """One cohesive service behind the palette, panes, and API namespace."""

    clock: Clock = field(default_factory=SystemClock)
    capabilities: Capabilities = field(default_factory=Capabilities)
    bus: EventBus = field(default_factory=EventBus)
    registry: CommandRegistry = field(default_factory=default_registry)
    navigation: NavigationGraph = field(default_factory=default_navigation)
    workspace: WorkspaceManager = field(default_factory=default_workspace)
    usage: UsageModel = field(default_factory=UsageModel)
    resolver: ContextResolver = field(default_factory=ContextResolver)
    policy: CommandPolicy = field(default_factory=CommandPolicy)
    recorder: MacroRecorder = field(default_factory=MacroRecorder)
    library: MacroLibrary = field(default_factory=MacroLibrary)
    focus: FocusSessionManager = field(default_factory=FocusSessionManager)
    actor_level: PermissionLevel = PermissionLevel.READ
    guard: CommandCapabilityGuard = field(init=False)

    def __post_init__(self) -> None:
        self.bus._clock = self.clock
        self.usage._clock = self.clock
        self.recorder.clock = self.clock
        self.focus.clock = self.clock
        self.guard = CommandCapabilityGuard(self.capabilities, self.policy)

    def _emit(self, kind: str, *, ref: str = "", request_id: str = "", **payload: Any) -> None:
        """Publish a structured, redaction-safe domain event."""
        subject = try_parse(ref) if ref else None
        self.bus.publish(make_event(kind, subject, **payload), request_id=request_id)

    def manifest(self) -> dict[str, Any]:
        """Return a data-only manifest for the frontend palette."""
        return {
            "commands": [spec.as_dict() for spec in self.registry.all()],
            "groups": [group.value for group in self.registry.groups()],
            "capabilities": self.capabilities.as_dict(),
            "permission": self.actor_level.value,
        }

    def list_commands(self, context: CommandContext | None = None) -> tuple[CommandSpec, ...]:
        """Return commands allowed for the current actor and context."""
        return self.guard.filter(self.registry.enabled(), context, actor_level=self.actor_level)

    def resolve_context(
        self,
        pane_id: str = "",
        *,
        entity: EntityRef | None = None,
        selection: tuple[EntityRef, ...] = (),
        tags: tuple[str, ...] = (),
    ) -> CommandContext:
        """Build a command context from live workspace and focus state."""
        target = pane_id or self.workspace.state.active_pane
        pane = next((item for item in self.workspace.panes() if item.id == target), None)
        context_entity = entity
        if context_entity is None and pane is not None and pane.context_ref:
            parsed = try_parse(pane.context_ref)
            if parsed is not None:
                context_entity = EntityRef(parsed)
        session = self.focus.current()
        return self.resolver.resolve(
            target,
            workspace_id=self.workspace.state.id,
            entity=context_entity,
            selection=selection,
            tags=tags,
            focus_active=session is not None and session.status.value == "active",
            capabilities=self.capabilities,
        )

    def suggest(
        self,
        query: str,
        context: CommandContext | None = None,
        *,
        limit: int = 12,
    ) -> tuple[CommandGroupResult, ...]:
        """Return grouped, ranked commands for a query."""
        active = context or self.resolve_context()
        hits = rank_commands(
            query,
            self.list_commands(active),
            active,
            resolver=self.resolver,
            usage=self.usage,
            limit=limit,
            now=self.clock.now_timestamp(),
        )
        return group_hits(hits)

    def _validate_arguments(
        self, spec: CommandSpec, invocation: CommandInvocation
    ) -> dict[str, str]:
        """Validate a structured invocation against a command contract."""
        arguments = dict(invocation.arguments)
        unknown = sorted(set(arguments) - set(spec.argument_names))
        if unknown:
            raise BindingError(f"Unknown argument(s): {', '.join(unknown)}")
        for name in spec.required_argument_names:
            if name not in arguments or not arguments[name]:
                raise BindingError(f"Missing required argument: {name}")
        validated: dict[str, str] = {}
        for name, value in arguments.items():
            argument = spec.argument(name)
            if argument is not None:
                validated[name] = argument.validate_value(value)
        return validated

    def _apply_effect(
        self,
        spec: CommandSpec,
        invocation: CommandInvocation,
        context: CommandContext,
    ) -> dict[str, Any]:
        """Apply a declarative effect; never interpret shell or arbitrary code."""
        args = invocation.arguments
        if spec.effect is CommandEffect.FOCUS:
            if spec.id == "session.start":
                session = self.focus.start(
                    args.get("label", "Focus"),
                    target=context.entity_ref,
                    restore_pane=context.pane_id,
                )
                self._emit(FOCUS_EVENT, session=session.as_dict(), action="started")
                return {"session": session.as_dict()}
            if spec.id == "session.pause":
                self._emit(FOCUS_EVENT, session=self.focus.pause().as_dict(), action="paused")
            elif spec.id == "session.resume":
                self._emit(FOCUS_EVENT, session=self.focus.resume().as_dict(), action="resumed")
            elif spec.id == "session.end":
                session = self.focus.end()
                self._emit(FOCUS_EVENT, session=session.as_dict(), action="ended")
                return {"session": session.as_dict(), "restore_pane": session.restore_pane}
            return {"focus": self.focus.status()}
        if spec.effect is CommandEffect.MACRO:
            if spec.id == "automation.record":
                macro = self.begin_macro(args.get("name", ""))
                return {"macro": macro.as_dict() if macro else self.recorder_status()}
            if spec.id == "automation.run":
                return {"steps": [item.as_dict() for item in self.run_macro(args.get("name", ""))]}
        if spec.effect is CommandEffect.OPEN_PANE:
            if spec.id == "view.split":
                pane = self.workspace.split(
                    context.pane_id,
                    args.get("orientation", "vertical"),
                    title=args.get("title", ""),
                )
                self._emit(WORKSPACE_EVENT, pane=pane.as_dict(), action="split")
                return {"pane": pane.as_dict(), "workspace": self.workspace.snapshot()}
            if spec.id == "view.close":
                pane = self.workspace.close(args.get("pane", context.pane_id))
                self._emit(WORKSPACE_EVENT, pane=pane.as_dict(), action="closed")
                return {"pane": pane.as_dict(), "workspace": self.workspace.snapshot()}
            if spec.id == "view.focus":
                pane = self.workspace.activate(args.get("pane", context.pane_id))
                return {"pane": pane.as_dict()}
        return {"context": context.as_dict(), "arguments": dict(args)}

    def execute(
        self,
        invocation: CommandInvocation,
        context: CommandContext | None = None,
        *,
        request_id: str = "",
    ) -> CommandResult:
        """Execute one structured command after all checks pass."""
        spec = self.registry.get(invocation.command_id)
        if spec is None:
            raise CommandDeniedError(
                CommandDenial(
                    reason=DenialReason.UNKNOWN_COMMAND,
                    command_id=invocation.command_id,
                    detail=f"Unknown command: {invocation.command_id}",
                )
            )
        active = context or self.resolve_context()
        self.guard.check(spec, active, actor_level=self.actor_level)
        validated = self._validate_arguments(spec, invocation)
        invocation = CommandInvocation(
            command_id=spec.id,
            arguments=validated,
            source=invocation.source,
            context_ref=invocation.context_ref or active.entity_ref,
        )
        self.usage.record(invocation, pane_id=active.pane_id, context_ref=active.entity_ref)
        if self.recorder.is_recording:
            self.recorder.capture(invocation)
        data = self._apply_effect(spec, invocation, active)
        self._emit(
            EXECUTED_EVENT,
            ref=active.entity_ref,
            request_id=request_id,
            command_id=spec.id,
            source=invocation.source,
            effect=spec.effect.value,
        )
        return CommandResult(
            invocation=invocation,
            accepted=True,
            message=f"Ran {spec.title}",
            data=data,
            event_kind=EXECUTED_EVENT,
        )

    def begin_macro(self, name: str) -> Macro | None:
        """Start recording a macro, or return None if already recording."""
        if self.recorder.is_recording:
            return None
        self.recorder.start(name)
        return None

    def recorder_status(self) -> dict[str, Any]:
        """Return recorder state for the UI."""
        return {
            "recording": self.recorder.is_recording,
            "steps": self.recorder.size,
        }

    def stop_macro(self) -> Macro:
        """Stop recording and store the resulting macro."""
        macro = self.recorder.stop()
        self.library.add(macro)
        self._emit(MACRO_EVENT, macro_id=macro.id, name=macro.name, steps=len(macro.steps))
        return macro

    def run_macro(
        self, name: str, values: dict[str, str] | None = None
    ) -> tuple[CommandInvocation, ...]:
        """Expand a stored macro into invocations without executing it here."""
        macro = self.library.find_by_name(name)
        if macro is None:
            raise MacroError(f"Unknown macro: {name}")
        return expand_macro(macro, values or {})

    def execute_macro(
        self,
        name: str,
        values: dict[str, str] | None = None,
        context: CommandContext | None = None,
    ) -> tuple[CommandResult, ...]:
        """Expand and execute a stored macro step by step."""
        results: list[CommandResult] = []
        for invocation in self.run_macro(name, values):
            results.append(self.execute(invocation, context))
        return tuple(results)

    def register_entity(self, ref: EntityRef, *, parent: str = "vault") -> NavNode:
        """Add an entity to the navigation graph for breadcrumbs."""
        node_id = str(ref)
        if not self.navigation.has(node_id):
            self.navigation.add_node(
                NavNode(
                    node_id,
                    ref.label or ref.entity_id.value,
                    kind=ref.kind.value,
                    parent=parent,
                    entity=ref,
                )
            )
            if self.navigation.has(parent):
                self.navigation.link(parent, node_id)
        return self.navigation.node(node_id)

    def breadcrumbs(self, ref: str) -> tuple[NavNode, ...]:
        """Return the navigation breadcrumb trail for a reference."""
        if not self.navigation.has(ref):
            return ()
        return self.navigation.breadcrumbs(ref)

    def focus_start(self, label: str, *, target: str = "", restore_pane: str = "") -> FocusSession:
        """Start a focus session directly."""
        session = self.focus.start(
            label, target=target, restore_pane=restore_pane or self.workspace.state.active_pane
        )
        self._emit(FOCUS_EVENT, session=session.as_dict(), action="started")
        return session

    def focus_end(self) -> FocusSession:
        """End the active focus session."""
        session = self.focus.end()
        self._emit(FOCUS_EVENT, session=session.as_dict(), action="ended")
        return session

    def snapshot(self) -> dict[str, Any]:
        """Return a complete command-center state snapshot."""
        return {
            "usage": self.usage.snapshot(),
            "macros": self.library.snapshot(),
            "focus": self.focus.snapshot(),
            "workspace": self.workspace.snapshot(),
            "navigation": self.navigation.snapshot(),
        }

    def restore(self, snapshot: dict[str, Any]) -> None:
        """Restore a complete command-center state snapshot."""
        for key, target in (
            ("usage", self.usage),
            ("macros", self.library),
            ("focus", self.focus),
        ):
            payload = snapshot.get(key)
            if isinstance(payload, dict):
                target.load(payload)
        workspace = snapshot.get("workspace")
        if isinstance(workspace, dict):
            self.workspace.restore(workspace)
        navigation = snapshot.get("navigation")
        if isinstance(navigation, dict):
            self.navigation.load(navigation)
