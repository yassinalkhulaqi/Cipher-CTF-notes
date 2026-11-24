"""Context resolution and availability rules for commands."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import Any

from redscribe.v3.capabilities import CAP_COMMANDS, Capabilities
from redscribe.v3.commands.types import CommandContext, CommandGroup, CommandSpec
from redscribe.v3.entities.types import EntityKind, EntityRef

ContextProvider = Callable[[str], CommandContext]


@dataclass(frozen=True, slots=True)
class ContextRule:
    """Declarative rule that enables a command in a context."""

    group: CommandGroup | None = None
    command_id: str = ""
    required_tag: str = ""
    required_capability: str = ""

    def matches(self, spec: CommandSpec, context: CommandContext) -> bool:
        """Return whether this rule applies to a command in a context."""
        if self.command_id and self.command_id != spec.id:
            return False
        if self.group is not None and self.group is not spec.group:
            return False
        if self.required_tag and self.required_tag not in context.tags:
            return False
        return not (
            self.required_capability and self.required_capability not in context.capabilities
        )


@dataclass(slots=True)
class ContextResolver:
    """Builds command contexts and computes context relevance."""

    providers: dict[str, ContextProvider] = field(default_factory=dict)
    rules: tuple[ContextRule, ...] = ()

    def add_provider(self, pane_id: str, provider: ContextProvider) -> None:
        """Register a context provider for one pane."""
        if not pane_id:
            raise ValueError("Pane id cannot be empty")
        self.providers[pane_id] = provider

    def resolve(
        self,
        pane_id: str,
        *,
        workspace_id: str = "main",
        entity: EntityRef | None = None,
        selection: tuple[EntityRef, ...] = (),
        tags: tuple[str, ...] = (),
        focus_active: bool = False,
        capabilities: Capabilities | None = None,
    ) -> CommandContext:
        """Resolve a context, preferring a registered pane provider."""
        active = capabilities or Capabilities()
        provider = self.providers.get(pane_id)
        if provider is not None:
            base = provider(pane_id)
            return CommandContext(
                pane_id=base.pane_id,
                workspace_id=base.workspace_id,
                entity=entity if entity is not None else base.entity,
                selection=selection or base.selection,
                tags=tags or base.tags,
                focus_active=focus_active or base.focus_active,
                capabilities=frozenset(active.enabled),
            )
        return CommandContext(
            pane_id=pane_id,
            workspace_id=workspace_id,
            entity=entity,
            selection=selection,
            tags=tags,
            focus_active=focus_active,
            capabilities=frozenset(active.enabled),
        )

    def is_available(self, spec: CommandSpec, context: CommandContext) -> bool:
        """Return whether a command may be shown in a context."""
        if spec.status.value != "enabled":
            return False
        if CAP_COMMANDS not in context.capabilities or spec.capability not in context.capabilities:
            return False
        if spec.requires_selection and not context.selection:
            return False
        if spec.target_kind is not None and not self._kind_matches(spec.target_kind, context):
            return False
        return not (self.rules and not any(rule.matches(spec, context) for rule in self.rules))

    @staticmethod
    def _kind_matches(kind: EntityKind, context: CommandContext) -> bool:
        """Check a command's target kind against the context entities."""
        if context.entity is not None and context.entity.kind is kind:
            return True
        return any(item.kind is kind for item in context.selection)

    def applicable(
        self, specs: Iterable[CommandSpec], context: CommandContext
    ) -> tuple[CommandSpec, ...]:
        """Filter commands to those available in a context."""
        return tuple(spec for spec in specs if self.is_available(spec, context))

    def weight(self, spec: CommandSpec, context: CommandContext) -> float:
        """Return a deterministic relevance boost for a command."""
        boost = 0.0
        if spec.target_kind is not None and self._kind_matches(spec.target_kind, context):
            boost += 0.45
        if context.focus_active and spec.group is CommandGroup.SESSION:
            boost += 0.3
        if not context.focus_active and spec.group is CommandGroup.SESSION:
            boost -= 0.1
        if context.selection and spec.group is CommandGroup.INSPECT:
            boost += 0.15
        if spec.requires_selection and context.selection:
            boost += 0.1
        return boost

    def describe(self, context: CommandContext) -> dict[str, Any]:
        """Return a UI-friendly summary of a resolved context."""
        return {
            "pane": context.pane_id,
            "workspace": context.workspace_id,
            "entity": context.entity_ref,
            "selection": list(context.selection_refs),
            "tags": list(context.tags),
            "focus_active": context.focus_active,
            "capabilities": sorted(context.capabilities),
        }
