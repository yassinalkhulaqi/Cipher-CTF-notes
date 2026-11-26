"""Domain operations for the universal capture inbox.

Four small collaborators do the work: :class:`CaptureParser` turns free text
into a structured draft, :class:`TemplateEngine` renders named templates with
strict placeholder checks, :class:`TriageMachine` owns the state graph, and
:class:`InboxService` coordinates them with storage and the event bus. Nothing
in this module executes user-supplied code; templates are substitutions over a
fixed placeholder grammar and all persistence is data-only.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass

from redscribe.v4.contracts import EntityKind
from redscribe.v4.events import DomainEvent, EventBus, EventKind, utc_now
from redscribe.v4.inbox.storage import InboxStore
from redscribe.v4.inbox.types import (
    FLAG_PATTERN,
    URL_PATTERN,
    CaptureDraft,
    CaptureItem,
    CaptureSource,
    TriageState,
    compute_content_hash,
    normalize_raw,
    normalize_tags,
    validate_confidence,
)

CODE_FENCE = "```"
TRAILING_PUNCTUATION = ".,;:!?)]}'\""
TEMPLATE_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,39}$")
PLACEHOLDER_PATTERN = re.compile(r"\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}")
MAX_TEMPLATE_LENGTH = 4000

DEFAULT_TEMPLATES: dict[str, str] = {
    "note": "{{title}}\n\n{{body}}\n\nTags: {{tags}}",
    "flag": "Flag: {{flag}}\nCapture: {{id}}\nNotes: {{note}}",
    "link": "[{{title}}]({{url}})\nCaptured: {{created_at}}\n{{note}}",
    "snippet": "Language: {{language}}\n```\n{{code}}\n```",
    "handoff": (
        "Capture {{id}}\nSource: {{source}}\nState: {{state}}\n"
        "Created: {{created_at}}\nTags: {{tags}}\n\n{{raw}}"
    ),
}

TRANSITIONS: dict[TriageState, frozenset[TriageState]] = {
    TriageState.UNTRIAGED: frozenset(
        {TriageState.ACCEPTED, TriageState.REJECTED, TriageState.ARCHIVED}
    ),
    TriageState.ACCEPTED: frozenset({TriageState.ARCHIVED}),
    TriageState.REJECTED: frozenset({TriageState.ARCHIVED}),
    TriageState.ARCHIVED: frozenset({TriageState.UNTRIAGED}),
}

ACTIONS: dict[str, TriageState] = {
    "accept": TriageState.ACCEPTED,
    "reject": TriageState.REJECTED,
    "archive": TriageState.ARCHIVED,
    "reset": TriageState.UNTRIAGED,
}

SOURCE_CONFIDENCE: dict[CaptureSource, float] = {
    CaptureSource.MANUAL: 0.55,
    CaptureSource.LINK: 0.82,
    CaptureSource.SNIPPET: 0.72,
    CaptureSource.FLAG: 0.94,
    CaptureSource.CLIPBOARD: 0.60,
}


class InboxError(Exception):
    """Base class for recoverable inbox domain errors."""


class CaptureNotFoundError(InboxError):
    """Raised when no capture has the requested id."""

    def __init__(self, item_id: str) -> None:
        super().__init__(f"capture not found: {item_id}")
        self.item_id = item_id


class TemplateError(InboxError):
    """Base class for template-related errors."""


class UnknownTemplateError(TemplateError):
    """Raised when a named template is not registered."""

    def __init__(self, name: str) -> None:
        super().__init__(f"unknown template: {name}")
        self.name = name


class MissingTemplateKeyError(TemplateError):
    """Raised when a template needs a placeholder the caller did not supply."""

    def __init__(self, key: str, template: str, missing: Sequence[str] = ()) -> None:
        super().__init__(f"missing template key '{key}' in {template}")
        self.key = key
        self.template = template
        self.missing = tuple(missing)


class TransitionError(InboxError):
    """Raised when a requested triage transition is not legal."""

    def __init__(
        self,
        source: TriageState,
        target: TriageState,
        legal: Sequence[TriageState] = (),
    ) -> None:
        super().__init__(f"illegal transition {source.value} -> {target.value}")
        self.source = source
        self.target = target
        self.legal = tuple(legal)


class CaptureParser:
    """Classify raw text and extract the signals used to enrich a capture."""

    def __init__(
        self,
        url_pattern: re.Pattern[str] = URL_PATTERN,
        flag_pattern: re.Pattern[str] = FLAG_PATTERN,
    ) -> None:
        self.url_pattern = url_pattern
        self.flag_pattern = flag_pattern

    def extract_urls(self, raw: str) -> tuple[str, ...]:
        """Return distinct, syntactically valid HTTP(S) URLs in encounter order."""
        text = normalize_raw(raw)
        urls: list[str] = []
        for match in self.url_pattern.finditer(text):
            candidate = match.group(0).rstrip(TRAILING_PUNCTUATION)
            parsed = re.match(r"^https?://([^/?#]+)", candidate, re.IGNORECASE)
            if parsed is None or not parsed.group(1):
                continue
            if candidate not in urls:
                urls.append(candidate)
        return tuple(urls)

    def first_url(self, raw: str) -> str | None:
        """Return the first URL in the text, if any."""
        urls = self.extract_urls(raw)
        return urls[0] if urls else None

    def detect_flags(self, raw: str) -> tuple[str, ...]:
        """Return distinct ``flag{...}`` tokens in encounter order."""
        text = normalize_raw(raw)
        flags: list[str] = []
        for match in self.flag_pattern.finditer(text):
            token = match.group(0)
            if token not in flags:
                flags.append(token)
        return tuple(flags)

    def looks_like_snippet(self, raw: str) -> bool:
        """Heuristically detect source code or structured multi-line text."""
        text = normalize_raw(raw)
        if CODE_FENCE in text:
            return True
        markers = ("def ", "class ", "function ", "const ", "import ", "#!/", "SELECT ", "<?php")
        if any(marker in text for marker in markers):
            return True
        if text.count(";") >= 2 and text.count("=") >= 1:
            return True
        return len(text.split(" ")) >= 12 and text.count(":") >= 3

    def tag_hints(self, raw: str) -> tuple[str, ...]:
        """Derive conservative, normalized tag hints from capture text."""
        text = normalize_raw(raw)
        hints: set[str] = set()
        if self.detect_flags(text):
            hints.add("flag")
        if self.extract_urls(text):
            hints.update({"link", "web"})
        if self.looks_like_snippet(text):
            hints.add("snippet")
        upper = text.upper()
        if "TODO" in upper:
            hints.add("todo")
        if "CVE-" in upper:
            hints.add("cve")
        if "NOTE:" in upper:
            hints.add("note")
        return normalize_tags(hints)

    def classify(
        self,
        raw: str,
        hint: CaptureSource | str | None = None,
    ) -> CaptureSource:
        """Infer a source from the text unless the caller asserted one."""
        if hint is not None:
            if isinstance(hint, CaptureSource):
                return hint
            if isinstance(hint, str):
                return CaptureSource.parse(hint)
            raise TypeError("hint must be a CaptureSource or source string")
        text = normalize_raw(raw)
        if self.detect_flags(text):
            return CaptureSource.FLAG
        if self.first_url(text) is not None:
            return CaptureSource.LINK
        if self.looks_like_snippet(text):
            return CaptureSource.SNIPPET
        return CaptureSource.MANUAL

    def confidence_for(self, raw: str, source: CaptureSource) -> float:
        """Score how confident the parser is in its classification."""
        if not isinstance(source, CaptureSource):
            raise TypeError("source must be a CaptureSource")
        text = normalize_raw(raw)
        score = SOURCE_CONFIDENCE[source]
        if self.first_url(text) is not None:
            score += 0.04
        if self.detect_flags(text):
            score += 0.03
        if len(text) >= 40:
            score += 0.03
        if source is CaptureSource.MANUAL and len(text) < 8:
            score -= 0.10
        return validate_confidence(round(score, 3))

    def parse(
        self,
        raw: str,
        source: CaptureSource | str | None = None,
        tags: Iterable[str] = (),
        confidence: float | None = None,
    ) -> CaptureDraft:
        """Build a fully enriched draft from raw text and optional overrides."""
        text = normalize_raw(raw)
        chosen = self.classify(text, source)
        urls = self.extract_urls(text)
        flags = self.detect_flags(text)
        combined_tags = normalize_tags([*self.tag_hints(text), *tuple(tags)])
        score = (
            self.confidence_for(text, chosen)
            if confidence is None
            else validate_confidence(confidence)
        )
        return CaptureDraft(
            raw=text,
            source=chosen,
            tags=combined_tags,
            confidence=score,
            urls=urls,
            flags=flags,
        )


class TemplateEngine:
    """Render named templates with strict ``{{placeholder}}`` substitution."""

    def __init__(self, templates: Mapping[str, str] | None = None) -> None:
        initial = dict(DEFAULT_TEMPLATES if templates is None else templates)
        for name, text in initial.items():
            self.validate_template(name, text)
        self._templates: dict[str, str] = initial

    def validate_template(self, name: str, text: str) -> tuple[str, ...]:
        """Validate template shape and return its placeholder keys."""
        if not TEMPLATE_NAME_PATTERN.match(name):
            raise ValueError(f"Invalid template name: {name}")
        if not isinstance(text, str) or not text.strip():
            raise ValueError(f"Template '{name}' must not be empty")
        if len(text) > MAX_TEMPLATE_LENGTH:
            raise ValueError(f"Template '{name}' is too long")
        keys = tuple(dict.fromkeys(match.group(1) for match in PLACEHOLDER_PATTERN.finditer(text)))
        return keys

    def register(self, name: str, text: str) -> None:
        """Add or replace a named template after validation."""
        self.validate_template(name, text)
        self._templates[name] = text

    def remove(self, name: str) -> bool:
        """Remove a template; return whether it existed."""
        return self._templates.pop(name, None) is not None

    def names(self) -> tuple[str, ...]:
        """Return registered template names in stable order."""
        return tuple(sorted(self._templates))

    def get(self, name: str) -> str:
        """Return a registered template or raise :class:`UnknownTemplateError`."""
        try:
            return self._templates[name]
        except KeyError as exc:
            raise UnknownTemplateError(name) from exc

    def keys_for(self, name: str) -> tuple[str, ...]:
        """Return the placeholder keys required by a template."""
        return self.validate_template(name, self.get(name))

    def render_text(self, text: str, values: Mapping[str, object], name: str = "inline") -> str:
        """Substitute placeholders, failing on the first missing key."""
        keys = tuple(dict.fromkeys(match.group(1) for match in PLACEHOLDER_PATTERN.finditer(text)))
        missing = tuple(key for key in keys if key not in values)
        if missing:
            raise MissingTemplateKeyError(missing[0], name, missing)
        return PLACEHOLDER_PATTERN.sub(
            lambda match: str(values[match.group(1)]),
            text,
        )

    def render(self, name: str, values: Mapping[str, object]) -> str:
        """Render a registered template with the supplied values."""
        return self.render_text(self.get(name), values, name)

    def render_capture(self, item: CaptureItem, name: str = "handoff") -> str:
        """Render a capture using a derived, complete value mapping."""
        values = capture_values(item)
        if name == "flag" and item.raw.lower().startswith("flag"):
            values["flag"] = item.raw
        if name == "note":
            values.setdefault("title", item.source.label)
            values.setdefault("body", item.raw)
        if name == "link":
            values.setdefault("title", item.source.label)
            values.setdefault("note", item.raw)
        if name == "snippet":
            values.setdefault("language", "text")
            values.setdefault("code", item.raw)
        return self.render(name, values)


def capture_values(item: CaptureItem) -> dict[str, object]:
    """Derive the standard placeholder values for a capture item."""
    return {
        "id": item.id,
        "raw": item.raw,
        "source": item.source.value,
        "state": item.state.value,
        "tags": item.tag_line,
        "confidence": item.confidence,
        "created_at": item.created_at,
        "content_hash": item.content_hash,
        "flag": item.raw,
        "note": item.raw,
        "url": item.raw,
        "language": "text",
        "code": item.raw,
        "title": item.source.label,
        "body": item.raw,
    }


class TriageMachine:
    """A closed state machine for the four triage states."""

    def __init__(
        self,
        transitions: Mapping[TriageState, Iterable[TriageState]] | None = None,
    ) -> None:
        base: dict[TriageState, frozenset[TriageState]] = {
            state: frozenset(targets) for state, targets in TRANSITIONS.items()
        }
        if transitions is not None:
            base.update({state: frozenset(targets) for state, targets in transitions.items()})
        self._transitions = base

    def legal_targets(self, state: TriageState) -> tuple[TriageState, ...]:
        """Return legal targets for a state, sorted by value."""
        if not isinstance(state, TriageState):
            raise TypeError("state must be a TriageState")
        return tuple(sorted(self._transitions.get(state, frozenset()), key=lambda item: item.value))

    def can_transition(self, source: TriageState, target: TriageState) -> bool:
        """Whether moving from ``source`` to ``target`` is legal."""
        return target in self._transitions.get(source, frozenset())

    def transition(self, source: TriageState, target: TriageState) -> TriageState:
        """Apply a legal transition or raise :class:`TransitionError`."""
        if not isinstance(source, TriageState) or not isinstance(target, TriageState):
            raise TypeError("both states must be TriageState values")
        if not self.can_transition(source, target):
            raise TransitionError(source, target, self.legal_targets(source))
        return target

    def apply(self, item: CaptureItem, target: TriageState) -> CaptureItem:
        """Return the item moved to a legal target state."""
        return item.with_state(self.transition(item.state, target))

    def action_for(self, target: TriageState) -> str:
        """Map a target state to its UI action name."""
        for action, state in ACTIONS.items():
            if state is target:
                return action
        raise ValueError(f"no action maps to {target.value}")

    def target_for(self, action: str) -> TriageState:
        """Map a UI action name to its target state."""
        try:
            return ACTIONS[action.strip().casefold()]
        except KeyError as exc:
            raise ValueError(f"unknown triage action: {action}") from exc

    def validate_action(self, source: TriageState, action: str) -> TriageState:
        """Resolve an action and verify that its transition is legal."""
        return self.transition(source, self.target_for(action))

    def graph(self) -> dict[str, tuple[str, ...]]:
        """Serialize the transition graph for clients and documentation."""
        return {
            state.value: tuple(target.value for target in self.legal_targets(state))
            for state in TriageState
        }


@dataclass(frozen=True, slots=True)
class CaptureResult:
    """The outcome of a capture operation, including dedupe status."""

    item: CaptureItem
    created: bool


class InboxService:
    """Coordinate parsing, dedupe, triage, persistence, and events."""

    def __init__(
        self,
        store: InboxStore | None = None,
        parser: CaptureParser | None = None,
        templates: TemplateEngine | None = None,
        machine: TriageMachine | None = None,
        bus: EventBus | None = None,
        clock: Callable[[], str] = utc_now,
    ) -> None:
        self.store = store or InboxStore()
        self.parser = parser or CaptureParser()
        self.templates = templates or TemplateEngine()
        self.machine = machine or TriageMachine()
        self.bus = bus or EventBus()
        self.clock = clock

    def capture(
        self,
        raw: str,
        source: CaptureSource | str | None = None,
        tags: Iterable[str] = (),
        confidence: float | None = None,
        item_id: str | None = None,
    ) -> CaptureResult:
        """Parse and store a capture, returning the existing item on dedupe."""
        draft = self.parser.parse(raw, source=source, tags=tags, confidence=confidence)
        digest = compute_content_hash(draft.raw)
        existing = self.store.find_by_hash(digest)
        if existing is not None:
            return CaptureResult(item=existing, created=False)
        item = draft.to_item(item_id=item_id, created_at=self.clock())
        self.store.insert(item)
        self.bus.publish(
            DomainEvent(
                kind=EventKind.CAPTURE_CREATED,
                aggregate_id=item.id,
                aggregate_kind=EntityKind.INBOX_ITEM,
                payload={
                    "source": item.source.value,
                    "state": item.state.value,
                    "tags": list(item.tags),
                    "confidence": item.confidence,
                    "content_hash": item.content_hash,
                    "raw_length": len(item.raw),
                },
            )
        )
        return CaptureResult(item=item, created=True)

    def capture_many(self, raws: Iterable[str]) -> tuple[CaptureResult, ...]:
        """Capture several raw texts in order."""
        return tuple(self.capture(raw) for raw in raws)

    def get(self, item_id: str) -> CaptureItem:
        """Fetch one capture or raise :class:`CaptureNotFoundError`."""
        item = self.store.get(item_id)
        if item is None:
            raise CaptureNotFoundError(item_id)
        return item

    def triage(
        self,
        item_id: str,
        target: TriageState | str,
        actor: str = "local",
    ) -> CaptureItem:
        """Move a capture to a legal triage state and emit an event."""
        item = self.get(item_id)
        parsed = target if isinstance(target, TriageState) else TriageState.parse(target)
        updated = self.machine.apply(item, parsed)
        self.store.update(updated)
        self.bus.publish(
            DomainEvent(
                kind=EventKind.CAPTURE_TRAGED,
                aggregate_id=item.id,
                aggregate_kind=EntityKind.INBOX_ITEM,
                payload={
                    "from_state": item.state.value,
                    "to_state": updated.state.value,
                    "actor": actor[:120] or "local",
                    "tags": list(updated.tags),
                },
            )
        )
        return updated

    def accept(self, item_id: str, actor: str = "local") -> CaptureItem:
        """Shortcut for accepting a capture."""
        return self.triage(item_id, TriageState.ACCEPTED, actor)

    def reject(self, item_id: str, actor: str = "local") -> CaptureItem:
        """Shortcut for rejecting a capture."""
        return self.triage(item_id, TriageState.REJECTED, actor)

    def archive(self, item_id: str, actor: str = "local") -> CaptureItem:
        """Shortcut for archiving a capture."""
        return self.triage(item_id, TriageState.ARCHIVED, actor)

    def list(
        self,
        state: TriageState | str | None = None,
        source: CaptureSource | str | None = None,
        tag: str | None = None,
        query: str | None = None,
    ) -> tuple[CaptureItem, ...]:
        """List captures with optional state, source, tag, and text filters."""
        parsed_state = (
            None
            if state is None
            else (state if isinstance(state, TriageState) else TriageState.parse(state))
        )
        parsed_source = (
            None
            if source is None
            else (source if isinstance(source, CaptureSource) else CaptureSource.parse(source))
        )
        return self.store.list(
            state=parsed_state,
            source=parsed_source,
            tag=tag,
            query=query,
        )

    def stats(self) -> dict[str, int]:
        """Return counts by state and source for the inbox dashboard."""
        items = self.store.list()
        counts: dict[str, int] = {"total": len(items)}
        for state in TriageState:
            counts[f"state_{state.value}"] = sum(1 for item in items if item.state is state)
        for source in CaptureSource:
            counts[f"source_{source.value}"] = sum(1 for item in items if item.source is source)
        return counts

    def render(self, item_id: str, template: str = "handoff") -> str:
        """Render a named template for a stored capture."""
        return self.templates.render_capture(self.get(item_id), template)

    def remove(self, item_id: str) -> bool:
        """Delete a capture from the store."""
        return self.store.delete(item_id)

    def export_json(self) -> str:
        """Serialize the whole inbox to JSON."""
        return self.store.export_json()

    def import_json(self, text: str) -> int:
        """Import captures from JSON, revalidating every item."""
        return self.store.import_json(text)

    @property
    def total(self) -> int:
        """Number of stored captures."""
        return len(self.store)


__all__ = [
    "ACTIONS",
    "CODE_FENCE",
    "DEFAULT_TEMPLATES",
    "SOURCE_CONFIDENCE",
    "TRANSITIONS",
    "CaptureNotFoundError",
    "CaptureParser",
    "CaptureResult",
    "InboxError",
    "InboxService",
    "MissingTemplateKeyError",
    "TemplateEngine",
    "TemplateError",
    "TransitionError",
    "TriageMachine",
    "UnknownTemplateError",
    "capture_values",
]
