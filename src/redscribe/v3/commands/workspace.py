"""Resizable multi-pane workspace with per-pane context and persistence."""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from enum import Enum
from typing import Any, Protocol, runtime_checkable

from redscribe.v3.entities.types import EntityKind

PANE_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_.:-]{0,79}$")
MIN_RATIO = 0.1
MAX_RATIO = 0.9


class WorkspaceError(ValueError):
    """Raised for invalid workspace operations."""


class PaneOrientation(str, Enum):
    """Direction in which a pane split is divided."""

    HORIZONTAL = "horizontal"
    VERTICAL = "vertical"

    @classmethod
    def parse(cls, value: str) -> PaneOrientation:
        """Parse an orientation, accepting the row/column aliases."""
        normalized = value.strip().casefold()
        if normalized in ("row", "horizontal"):
            return cls.HORIZONTAL
        if normalized in ("column", "vertical"):
            return cls.VERTICAL
        raise WorkspaceError(f"Unknown pane orientation: {value}")


@dataclass(frozen=True, slots=True)
class PaneSpec:
    """Declarative state for one workspace pane."""

    id: str
    title: str
    kind: str = "note"
    context_ref: str = ""
    size: float = 1.0
    min_size: float = MIN_RATIO
    pinned: bool = False
    closable: bool = True

    def __post_init__(self) -> None:
        if not PANE_ID_PATTERN.fullmatch(self.id):
            raise WorkspaceError(f"Invalid pane id: {self.id}")
        if not self.title.strip():
            raise WorkspaceError("Pane title cannot be blank")
        if not 0.0 < self.size <= 1.0:
            raise WorkspaceError("Pane size must be in (0, 1]")
        if not MIN_RATIO <= self.min_size <= MAX_RATIO:
            raise WorkspaceError("Pane min_size is out of range")

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {
            "id": self.id,
            "title": self.title,
            "kind": self.kind,
            "context_ref": self.context_ref,
            "size": self.size,
            "min_size": self.min_size,
            "pinned": self.pinned,
            "closable": self.closable,
        }


@dataclass(frozen=True, slots=True)
class PaneNode:
    """A leaf pane or a binary split of two pane subtrees."""

    pane: PaneSpec | None = None
    orientation: PaneOrientation | None = None
    children: tuple[PaneNode, ...] = ()
    ratio: float = 1.0

    def __post_init__(self) -> None:
        if self.pane is not None:
            if self.children or self.orientation is not None:
                raise WorkspaceError("A pane leaf cannot have children")
            return
        if self.orientation is None or len(self.children) != 2:
            raise WorkspaceError("A pane split needs an orientation and two children")
        if not MIN_RATIO <= self.ratio <= MAX_RATIO:
            raise WorkspaceError("Split ratio is out of range")

    @property
    def is_leaf(self) -> bool:
        """Whether this node holds a single pane."""
        return self.pane is not None

    @classmethod
    def leaf(cls, pane: PaneSpec) -> PaneNode:
        """Build a leaf node."""
        return cls(pane=pane)

    @classmethod
    def branch(
        cls,
        first: PaneNode,
        second: PaneNode,
        orientation: PaneOrientation,
        ratio: float = 0.5,
    ) -> PaneNode:
        """Build a split node."""
        return cls(orientation=orientation, children=(first, second), ratio=ratio)

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        if self.pane is not None:
            return {"pane": self.pane.as_dict()}
        return {
            "orientation": self.orientation.value if self.orientation else "vertical",
            "ratio": self.ratio,
            "children": [child.as_dict() for child in self.children],
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> PaneNode:
        """Rebuild a pane tree from persisted data."""
        raw_pane = payload.get("pane")
        if isinstance(raw_pane, dict):
            return cls.leaf(
                PaneSpec(
                    id=str(raw_pane.get("id", "")),
                    title=str(raw_pane.get("title", "")),
                    kind=str(raw_pane.get("kind", "note")),
                    context_ref=str(raw_pane.get("context_ref", "")),
                    size=float(raw_pane.get("size", 1.0)),
                    min_size=float(raw_pane.get("min_size", MIN_RATIO)),
                    pinned=bool(raw_pane.get("pinned", False)),
                    closable=bool(raw_pane.get("closable", True)),
                )
            )
        raw_children = payload.get("children", ())
        if not isinstance(raw_children, (list, tuple)) or len(raw_children) != 2:
            raise WorkspaceError("Pane split must have two children")
        return cls.branch(
            cls.from_dict(raw_children[0])
            if isinstance(raw_children[0], dict)
            else cls.leaf(_fallback_pane()),
            cls.from_dict(raw_children[1])
            if isinstance(raw_children[1], dict)
            else cls.leaf(_fallback_pane()),
            PaneOrientation.parse(str(payload.get("orientation", "vertical"))),
            float(payload.get("ratio", 0.5)),
        )


def _fallback_pane() -> PaneSpec:
    """Build a valid placeholder pane for damaged snapshots."""
    return PaneSpec(id="pane:recovered", title="Recovered pane")


def _node_at(root: PaneNode, path: tuple[int, ...]) -> PaneNode:
    """Walk to a node by child-index path."""
    node = root
    for index in path:
        if node.is_leaf or index >= len(node.children):
            raise WorkspaceError(f"Invalid pane path: {path}")
        node = node.children[index]
    return node


def _replace_at(root: PaneNode, path: tuple[int, ...], replacement: PaneNode) -> PaneNode:
    """Return a new tree with a node replaced at a path."""
    if not path:
        return replacement
    index = path[0]
    node = _node_at(root, path[:-1])
    if node.is_leaf or index >= len(node.children):
        raise WorkspaceError(f"Invalid pane path: {path}")
    children = list(node.children)
    children[index] = _replace_at(children[index], path[1:], replacement)
    return PaneNode.branch(
        children[0], children[1], node.orientation or PaneOrientation.VERTICAL, node.ratio
    )


@dataclass(slots=True)
class PaneTree:
    """Immutable-by-convention binary pane tree."""

    root: PaneNode

    def leaves(self) -> tuple[PaneSpec, ...]:
        """Return all pane leaves in display order."""
        if self.root.is_leaf:
            return (self.root.pane,) if self.root.pane else ()
        result: list[PaneSpec] = []
        for child in self.root.children:
            result.extend(PaneTree(child).leaves())
        return tuple(result)

    def paths(self) -> dict[str, tuple[int, ...]]:
        """Map pane ids to their tree paths."""
        found: dict[str, tuple[int, ...]] = {}

        def walk(node: PaneNode, path: tuple[int, ...]) -> None:
            if node.pane is not None:
                found[node.pane.id] = path
                return
            for index, child in enumerate(node.children):
                walk(child, (*path, index))

        walk(self.root, ())
        return found

    def find(self, pane_id: str) -> tuple[int, ...] | None:
        """Return the path of a pane, if present."""
        return self.paths().get(pane_id)

    def node_at(self, path: tuple[int, ...]) -> PaneNode:
        """Return the node at a path."""
        return _node_at(self.root, path)

    def insert(
        self,
        pane_id: str,
        pane: PaneSpec,
        orientation: PaneOrientation,
        *,
        ratio: float = 0.5,
        after: bool = True,
    ) -> PaneTree:
        """Split an existing pane and insert a new sibling."""
        path = self.find(pane_id)
        if path is None:
            raise WorkspaceError(f"Unknown pane: {pane_id}")
        if any(item.id == pane.id for item in self.leaves()):
            raise WorkspaceError(f"Pane already exists: {pane.id}")
        existing = _node_at(self.root, path)
        if not existing.is_leaf or existing.pane is None:
            raise WorkspaceError("Can only split a leaf pane")
        first, second = (
            (existing, PaneNode.leaf(pane)) if after else (PaneNode.leaf(pane), existing)
        )
        branch = PaneNode.branch(first, second, orientation, ratio if after else 1.0 - ratio)
        return PaneTree(_replace_at(self.root, path, branch))

    def remove(self, pane_id: str) -> PaneTree:
        """Remove a pane, collapsing its parent split."""
        paths = self.paths()
        path = paths.get(pane_id)
        if path is None:
            raise WorkspaceError(f"Unknown pane: {pane_id}")
        if not path:
            raise WorkspaceError("Cannot close the last pane")
        target = _node_at(self.root, path)
        if target.pane is not None and not target.pane.closable:
            raise WorkspaceError(f"Pane is pinned: {pane_id}")
        parent_path = path[:-1]
        sibling_index = 1 - path[-1]
        sibling = _node_at(self.root, (*parent_path, sibling_index))
        return PaneTree(_replace_at(self.root, parent_path, sibling))

    def resize(self, pane_id: str, size: float) -> PaneTree:
        """Adjust the split ratio governing a pane."""
        if not MIN_RATIO <= size <= MAX_RATIO:
            raise WorkspaceError("Pane size is out of range")
        path = self.find(pane_id)
        if path is None or not path:
            raise WorkspaceError(f"Pane has no resizable parent: {pane_id}")
        parent = _node_at(self.root, path[:-1])
        if parent.is_leaf or parent.orientation is None:
            raise WorkspaceError(f"Pane has no resizable parent: {pane_id}")
        ratio = size if path[-1] == 0 else 1.0 - size
        replacement = PaneNode.branch(
            parent.children[0], parent.children[1], parent.orientation, ratio
        )
        return PaneTree(_replace_at(self.root, path[:-1], replacement))

    def update(self, pane_id: str, **changes: Any) -> PaneTree:
        """Return a tree with one pane's declarative fields updated."""
        path = self.find(pane_id)
        if path is None:
            raise WorkspaceError(f"Unknown pane: {pane_id}")
        node = _node_at(self.root, path)
        if node.pane is None:
            raise WorkspaceError(f"Node is not a pane: {pane_id}")
        allowed = {"title", "kind", "context_ref", "size", "pinned", "closable"}
        unknown = set(changes) - allowed
        if unknown:
            raise WorkspaceError(f"Unsupported pane fields: {', '.join(sorted(unknown))}")
        return PaneTree(_replace_at(self.root, path, PaneNode.leaf(replace(node.pane, **changes))))

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {"root": self.root.as_dict()}

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> PaneTree:
        """Rebuild a pane tree from persisted data."""
        root = payload.get("root")
        if not isinstance(root, dict):
            raise WorkspaceError("Pane tree snapshot needs a root")
        return cls(PaneNode.from_dict(root))


@dataclass(frozen=True, slots=True)
class WorkspaceState:
    """Complete workspace snapshot."""

    id: str
    tree: PaneTree
    active_pane: str

    def __post_init__(self) -> None:
        pane_ids = {pane.id for pane in self.tree.leaves()}
        if self.active_pane not in pane_ids:
            raise WorkspaceError("Active pane must be part of the workspace")

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {
            "id": self.id,
            "active_pane": self.active_pane,
            "tree": self.tree.as_dict(),
        }


@runtime_checkable
class PanePersistence(Protocol):
    """Storage seam for persisting workspace layout as data."""

    def load(self) -> dict[str, Any] | None:
        """Return a stored snapshot, if any."""
        ...

    def save(self, snapshot: dict[str, Any]) -> None:
        """Persist a snapshot."""
        ...


@dataclass(slots=True)
class MemoryPanePersistence:
    """In-memory persistence used offline and in tests."""

    _snapshot: dict[str, Any] | None = None

    def load(self) -> dict[str, Any] | None:
        """Return the stored snapshot."""
        return None if self._snapshot is None else dict(self._snapshot)

    def save(self, snapshot: dict[str, Any]) -> None:
        """Store a copy of the snapshot."""
        self._snapshot = dict(snapshot)


@dataclass(slots=True)
class WorkspaceManager:
    """Mutates workspace state through validated, reversible operations."""

    state: WorkspaceState
    persistence: PanePersistence | None = None

    def panes(self) -> tuple[PaneSpec, ...]:
        """Return all panes in display order."""
        return self.state.tree.leaves()

    def active(self) -> PaneSpec:
        """Return the active pane."""
        for pane in self.panes():
            if pane.id == self.state.active_pane:
                return pane
        raise WorkspaceError("Active pane is missing")

    def activate(self, pane_id: str) -> PaneSpec:
        """Make a pane active."""
        if self.state.tree.find(pane_id) is None:
            raise WorkspaceError(f"Unknown pane: {pane_id}")
        self.state = replace(self.state, active_pane=pane_id)
        return self.active()

    def split(
        self,
        pane_id: str,
        orientation: PaneOrientation | str,
        *,
        new_pane_id: str = "",
        title: str = "",
        ratio: float = 0.5,
    ) -> PaneSpec:
        """Split a pane and activate the new sibling."""
        parsed = (
            orientation
            if isinstance(orientation, PaneOrientation)
            else PaneOrientation.parse(orientation)
        )
        identifier = new_pane_id or f"pane:{len(self.panes()) + 1}"
        pane = PaneSpec(id=identifier, title=title or f"Pane {len(self.panes()) + 1}")
        self.state = replace(
            self.state,
            tree=self.state.tree.insert(pane_id, pane, parsed, ratio=ratio),
            active_pane=identifier,
        )
        return self.active()

    def resize(self, pane_id: str, size: float) -> PaneTree:
        """Resize a pane within its parent split."""
        self.state = replace(self.state, tree=self.state.tree.resize(pane_id, size))
        return self.state.tree

    def close(self, pane_id: str) -> PaneSpec:
        """Close a pane and restore a valid active pane."""
        tree = self.state.tree.remove(pane_id)
        remaining = tree.leaves()
        active = (
            self.state.active_pane
            if any(p.id == self.state.active_pane for p in remaining)
            else remaining[0].id
        )
        self.state = replace(self.state, tree=tree, active_pane=active)
        return self.active()

    def set_context(self, pane_id: str, context_ref: str) -> PaneSpec:
        """Set the per-pane entity context."""
        self.state = replace(
            self.state, tree=self.state.tree.update(pane_id, context_ref=context_ref)
        )
        return next(pane for pane in self.panes() if pane.id == pane_id)

    def rename(self, pane_id: str, title: str) -> PaneSpec:
        """Rename a pane."""
        self.state = replace(self.state, tree=self.state.tree.update(pane_id, title=title))
        return next(pane for pane in self.panes() if pane.id == pane_id)

    def snapshot(self) -> dict[str, Any]:
        """Return a serializable workspace snapshot."""
        return self.state.as_dict()

    def save(self) -> dict[str, Any]:
        """Persist and return the current snapshot."""
        snapshot = self.snapshot()
        if self.persistence is not None:
            self.persistence.save(snapshot)
        return snapshot

    def restore(self, snapshot: dict[str, Any]) -> None:
        """Restore a workspace snapshot, validating its panes."""
        raw_tree = snapshot.get("tree")
        if not isinstance(raw_tree, dict):
            raise WorkspaceError("Workspace snapshot needs a tree")
        root = PaneNode.from_dict(raw_tree.get("root", {}))
        self.state = WorkspaceState(
            id=str(snapshot.get("id", "main")),
            tree=PaneTree(root),
            active_pane=str(snapshot.get("active_pane", "")),
        )

    def load(self) -> bool:
        """Load a persisted snapshot, returning whether one existed."""
        if self.persistence is None:
            return False
        snapshot = self.persistence.load()
        if snapshot is None:
            return False
        self.restore(snapshot)
        return True


def default_workspace() -> WorkspaceManager:
    """Build the initial single-pane workspace."""
    pane = PaneSpec(
        id="pane:main",
        title="Main workspace",
        kind=EntityKind.NOTE.value,
        context_ref="",
    )
    return WorkspaceManager(
        WorkspaceState(id="main", tree=PaneTree(PaneNode.leaf(pane)), active_pane=pane.id)
    )
