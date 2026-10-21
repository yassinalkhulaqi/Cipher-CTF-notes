"""Typed data objects exchanged between the vault and the UI."""

from __future__ import annotations

from dataclasses import dataclass, field

STATUSES: tuple[str, ...] = ("todo", "active", "done", "blocked")
STATUS_LABELS: dict[str, str] = {
    "todo": "Open",
    "active": "Active",
    "done": "Done",
    "blocked": "Blocked",
}
STATUS_ICONS: dict[str, str] = {
    "todo": "○",
    "active": "●",
    "done": "✓",
    "blocked": "⊘",
}
DIFFICULTIES: tuple[str, ...] = ("", "easy", "medium", "hard", "insane")
DIFFICULTY_LABELS: dict[str, str] = {
    "": "Unrated",
    "easy": "Easy",
    "medium": "Medium",
    "hard": "Hard",
    "insane": "Insane",
}
KINDS: tuple[str, ...] = ("folder", "note")


@dataclass(frozen=True, slots=True)
class Node:
    """An immutable folder or note snapshot loaded from the vault."""

    id: int
    parent_id: int | None
    title: str
    kind: str
    content: str
    tags: str
    target: str
    status: str
    difficulty: str
    flag: str
    pinned: bool
    sort_order: int
    created_at: str
    updated_at: str
    deleted_at: str | None = None

    def __post_init__(self) -> None:
        if self.kind not in KINDS:
            raise ValueError(f"Unknown node kind: {self.kind}")
        if self.status not in STATUSES:
            raise ValueError(f"Unknown status: {self.status}")
        if self.difficulty not in DIFFICULTIES:
            raise ValueError(f"Unknown difficulty: {self.difficulty}")

    @property
    def is_folder(self) -> bool:
        return self.kind == "folder"

    @property
    def is_note(self) -> bool:
        return self.kind == "note"

    @property
    def is_trashed(self) -> bool:
        return self.deleted_at is not None

    @property
    def tag_list(self) -> list[str]:
        return [tag.strip() for tag in self.tags.split(",") if tag.strip()]

    @property
    def status_label(self) -> str:
        return STATUS_LABELS.get(self.status, self.status.title())

    @property
    def status_icon(self) -> str:
        return STATUS_ICONS.get(self.status, "○")

    @property
    def difficulty_label(self) -> str:
        return DIFFICULTY_LABELS.get(self.difficulty, self.difficulty.title())


@dataclass(frozen=True, slots=True)
class SearchHit:
    node_id: int
    title: str
    path: str
    snippet: str
    rank: float = 0.0


@dataclass(frozen=True, slots=True)
class FlagHit:
    flag: str
    node_id: int
    title: str
    path: str
    manual: bool = False


@dataclass(frozen=True, slots=True)
class Snippet:
    title: str
    command: str
    description: str = ""
    tags: str = ""
    builtin: bool = False
    builtin_key: str = ""
    id: int | None = None

    @property
    def tag_list(self) -> list[str]:
        return [tag.strip() for tag in self.tags.split(",") if tag.strip()]

    @property
    def category(self) -> str:
        tags = self.tag_list
        return tags[0] if tags else "misc"


@dataclass(frozen=True, slots=True)
class VaultStats:
    notes: int = 0
    folders: int = 0
    flags: int = 0
    targets: int = 0
    tags: int = 0
    pinned: int = 0
    trashed: int = 0


@dataclass(frozen=True, slots=True)
class TagCount:
    tag: str
    count: int


@dataclass(frozen=True, slots=True)
class Template:
    key: str
    name: str
    description: str
    content: str
    tags: str = ""
    status: str = "todo"
    default_title: str = "Untitled"
    glyph: str = "◆"


@dataclass(slots=True)
class NodeTree:
    """In-memory tree used to render the sidebar efficiently."""

    node: Node
    children: list[NodeTree] = field(default_factory=list)
    depth: int = 0
