"""Offline DOT, JSON, and Mermaid exporters for the graph workbench.

Exporters are pure string builders: no subprocesses, no network calls, and no
external assets. All labels are escaped for their target grammar so that entity
titles can never break out of the generated document.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum
from typing import Any

from redscribe.v3.graph_workbench.clustering import ClusterResult
from redscribe.v3.graph_workbench.model import WorkbenchGraph

DOT_MIME = "text/vnd.graphviz"
JSON_MIME = "application/json"
MERMAID_MIME = "text/plain"


class ExportFormat(str, Enum):
    """Supported export grammars."""

    DOT = "dot"
    JSON = "json"
    MERMAID = "mermaid"

    @classmethod
    def parse(cls, value: str) -> ExportFormat:
        """Parse a format name with a stable error."""
        normalized = value.strip().casefold()
        for item in cls:
            if item.value == normalized:
                return item
        raise ValueError(
            f"Unknown export format '{value}'; available: {', '.join(item.value for item in cls)}"
        )


EXPORT_FORMATS: tuple[str, ...] = tuple(item.value for item in ExportFormat)


@dataclass(frozen=True, slots=True)
class ExportResult:
    """One rendered export artifact."""

    fmt: str
    mime: str
    content: str
    node_count: int
    edge_count: int

    @property
    def size(self) -> int:
        """Return the rendered content length in characters."""
        return len(self.content)

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {
            "format": self.fmt,
            "mime": self.mime,
            "content": self.content,
            "node_count": self.node_count,
            "edge_count": self.edge_count,
            "size": self.size,
        }


def _dot_escape(value: str) -> str:
    """Escape a string for a quoted DOT attribute."""
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\r", " ").replace("\n", "\\n")


def _dot_id(value: str) -> str:
    """Return a quoted DOT node identifier."""
    return f'"{_dot_escape(value)}"'


def _mermaid_escape(value: str) -> str:
    """Escape a string for a Mermaid bracket label."""
    return (
        value.replace("&", "&amp;")
        .replace('"', "#quot;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace("\r", " ")
        .replace("\n", "<br/>")
        .replace("|", "&#124;")
    )


def _safe_class(kind: str) -> str:
    """Turn a kind string into a stable Mermaid class name."""
    cleaned = "".join(char if char.isalnum() else "_" for char in kind.casefold())
    return f"kind_{cleaned.strip('_') or 'default'}"


def _short_label(graph: WorkbenchGraph, node_id: str, max_length: int = 42) -> str:
    """Return a compact, single-line label for diagram nodes."""
    label = " ".join(graph.node(node_id).label.split())
    if len(label) <= max_length:
        return label
    return label[: max_length - 1].rstrip() + "…"


def to_dot(
    graph: WorkbenchGraph,
    *,
    rankdir: str = "LR",
    highlight: frozenset[str] | set[str] = frozenset(),
    clusters: ClusterResult | None = None,
) -> str:
    """Render a graph as a DOT directed graph."""
    if rankdir not in ("LR", "TB"):
        raise ValueError("rankdir must be LR or TB")
    lines = [
        "digraph graph_workbench {",
        f"  rankdir={rankdir};",
        '  graph [bgcolor="transparent", pad="0.4"];',
        '  node [shape="box", style="rounded,filled", fontname="sans-serif"];',
        '  edge [fontname="sans-serif", fontsize="10"];',
    ]
    members: dict[str, list[str]] = {}
    if clusters is not None:
        for cluster in clusters.clusters:
            members[cluster.key] = [
                node_id for node_id in cluster.node_ids if node_id in graph.nodes
            ]
    if members:
        for index, (key, node_ids) in enumerate(sorted(members.items())):
            if not node_ids:
                continue
            available = clusters.clusters if clusters else ()
            label = _dot_escape(next(cluster.label for cluster in available if cluster.key == key))
            lines.append(f"  subgraph cluster_{index} {{")
            lines.append(f'    label="{label}";')
            lines.append('    style="dashed";')
            for node_id in node_ids:
                lines.append(f"    {_dot_id(node_id)};")
            lines.append("  }")
    for node_id in graph.node_ids:
        node = graph.node(node_id)
        color = graph.kind_color(node.kind)
        pen = "#f59e0b" if node_id in highlight else color
        width = 2.5 if node_id in highlight else 1.0
        lines.append(
            f"  {_dot_id(node_id)} ["
            f'label="{_dot_escape(_short_label(graph, node_id))}", '
            f'fillcolor="{_dot_escape(color)}", color="{_dot_escape(pen)}", '
            f'penwidth={width:.1f}, tooltip="{_dot_escape(node.title)}"];'
        )
    for edge_key in graph.edge_keys:
        edge = graph.edges[edge_key]
        lines.append(
            f"  {_dot_id(edge.source)} -> {_dot_id(edge.target)} ["
            f'label="{_dot_escape(edge.label or edge.kind.value)}", '
            f'color="{_dot_escape(graph.kind_color(edge.kind.value))}"];'
        )
    lines.append("}")
    return "\n".join(lines)


def to_json(
    graph: WorkbenchGraph,
    *,
    pretty: bool = False,
    include_metadata: bool = True,
) -> str:
    """Render a graph as a stable JSON document."""
    payload: dict[str, Any] = {
        "version": 1,
        "generator": "redscribe.graph_workbench",
        "graph": graph.as_dict(include_metadata=include_metadata),
    }
    indent = 2 if pretty else None
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=indent)


def to_mermaid(
    graph: WorkbenchGraph,
    *,
    direction: str = "LR",
    clusters: ClusterResult | None = None,
) -> str:
    """Render a graph as a Mermaid flowchart."""
    if direction not in ("LR", "TB", "RL", "BT"):
        raise ValueError("Unsupported Mermaid direction")
    identifiers = {node_id: f"n{index}" for index, node_id in enumerate(graph.node_ids, start=1)}
    lines = [f"flowchart {direction}"]
    if clusters is not None:
        for cluster in clusters.clusters:
            members = [identifiers[item] for item in cluster.node_ids if item in identifiers]
            if not members:
                continue
            group = _safe_class(cluster.key)
            lines.append(f'  subgraph SG_{group}["{_mermaid_escape(cluster.label)}"]')
            for member in members:
                lines.append(f"    {member}")
            lines.append("  end")
    for node_id in graph.node_ids:
        node = graph.node(node_id)
        lines.append(
            f'  {identifiers[node_id]}["{_mermaid_escape(_short_label(graph, node_id))}"]'
            f":::{_safe_class(node.kind)}"
        )
    for key in graph.edge_keys:
        edge = graph.edges[key]
        lines.append(
            f"  {identifiers[edge.source]} -->|{_mermaid_escape(edge.label or edge.kind.value)}| "
            f"{identifiers[edge.target]}"
        )
    for kind in sorted({node.kind for node in graph.nodes.values()}):
        color = _mermaid_escape(graph.kind_color(kind))
        lines.append(f"  classDef {_safe_class(kind)} fill:{color},stroke:{color},color:#0f172a")
    return "\n".join(lines)


def export_graph(
    graph: WorkbenchGraph,
    fmt: ExportFormat | str = ExportFormat.JSON,
    *,
    clusters: ClusterResult | None = None,
    highlight: frozenset[str] | set[str] = frozenset(),
    pretty: bool = False,
    include_metadata: bool = True,
    direction: str = "LR",
) -> ExportResult:
    """Dispatch to a named exporter and return the rendered artifact."""
    parsed = fmt if isinstance(fmt, ExportFormat) else ExportFormat.parse(fmt)
    if parsed is ExportFormat.DOT:
        content = to_dot(graph, rankdir=direction, highlight=highlight, clusters=clusters)
        mime = DOT_MIME
    elif parsed is ExportFormat.MERMAID:
        content = to_mermaid(graph, direction=direction, clusters=clusters)
        mime = MERMAID_MIME
    else:
        content = to_json(graph, pretty=pretty, include_metadata=include_metadata)
        mime = JSON_MIME
    return ExportResult(
        fmt=parsed.value,
        mime=mime,
        content=content,
        node_count=len(graph.nodes),
        edge_count=len(graph.edges),
    )
