"""Export notes and vaults to Markdown and standalone HTML."""

from __future__ import annotations

import html
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from redscribe.content.markdown import DOCUMENT_CSS, render_html, render_markdown_body
from redscribe.domain.models import Node
from redscribe.domain.utils import safe_filename
from redscribe.storage.db import Vault

_VAULT_CSS = """
.vault-layout { display: grid; grid-template-columns: 300px minmax(0, 1fr); min-height: 100vh; }
.vault-nav {
  position: sticky; top: 0; height: 100vh; overflow-y: auto; padding: 24px 16px;
  background: var(--surface); border-right: 1px solid var(--border);
}
.vault-brand { color: var(--accent); font-size: 10px; font-weight: 700; letter-spacing: .22em; }
.vault-title { font-size: 20px; font-weight: 700; margin: 8px 0 4px; }
.vault-sub { color: var(--muted); font-size: 12px; margin-bottom: 18px; }
.vault-search {
  width: 100%; box-sizing: border-box; margin-bottom: 16px; padding: 8px 10px;
  border: 1px solid var(--border); border-radius: 6px; background: var(--surface-2);
  color: var(--text); font: inherit; font-size: 13px; outline: none;
}
.vault-search:focus { border-color: var(--accent); }
.nav-folder {
  color: var(--muted); font-size: 10px; font-weight: 700; letter-spacing: .12em;
  text-transform: uppercase; margin: 16px 8px 5px;
}
.nav-note {
  display: block; padding: 5px 8px; border-radius: 6px; color: var(--text);
  text-decoration: none; font-size: 13px; line-height: 1.35; border: 0;
}
.nav-note:hover { background: var(--surface-2); color: #fff; }
.nav-empty { color: var(--muted); font-size: 12px; padding: 8px; }
.vault-main { max-width: 920px; width: 100%; padding: 46px 42px 90px; }
.report-header { margin-bottom: 42px; padding-bottom: 24px; border-bottom: 1px solid var(--border); }
.report-kicker { color: var(--accent); font-size: 10px; font-weight: 700; letter-spacing: .22em; }
.report-title { font-size: 36px; line-height: 1.15; margin: 10px 0 6px; letter-spacing: -.02em; }
.report-summary { color: var(--muted); font-size: 14px; }
.note { padding-top: 8px; margin-top: 52px; border-top: 1px solid var(--border); }
.note:first-of-type { margin-top: 0; border-top: 0; }
.note-kicker { color: var(--muted); font-size: 11px; letter-spacing: .06em; text-transform: uppercase; }
.note-title { font-size: 30px; margin: 8px 0 10px; }
.note-meta { display: flex; flex-wrap: wrap; gap: 7px; margin: 10px 0 20px; }
.chip {
  display: inline-block; padding: 3px 8px; border-radius: 99px; background: var(--surface-2);
  border: 1px solid var(--border); color: var(--muted); font-size: 11px;
}
.chip.flag { color: var(--amber); font-family: "Cascadia Mono", Consolas, monospace; }
.chip.status-active { color: var(--blue); border-color: rgba(59,130,246,.4); }
.chip.status-done { color: var(--green); border-color: rgba(34,197,94,.35); }
.chip.status-blocked { color: var(--red); border-color: rgba(239,68,68,.35); }
.note .markdown > h1:first-child { margin-top: 0; }
.note-empty { color: var(--muted); font-style: italic; }
.vault-footer { margin-top: 72px; padding-top: 18px; border-top: 1px solid var(--border); color: var(--muted); font-size: 12px; }
@media (max-width: 860px) {
  .vault-layout { display: block; }
  .vault-nav { position: static; height: auto; }
  .vault-main { padding: 32px 22px 64px; }
}
@media print {
  .vault-layout { display: block; }
  .vault-nav { display: none; }
  .vault-main { max-width: none; padding: 0; }
  .report-header { border: 0; }
  .note { break-before: page; border-top: 0; }
  .note:first-of-type { break-before: auto; }
  .vault-footer { display: none; }
}
"""


def note_front_matter(node: Node) -> str:
    values: list[tuple[str, str]] = [
        ("title", node.title),
        ("status", node.status),
        ("created", node.created_at),
        ("updated", node.updated_at),
    ]
    if node.tags:
        values.append(("tags", node.tags))
    if node.target:
        values.append(("target", node.target))
    if node.difficulty:
        values.append(("difficulty", node.difficulty))
    if node.flag:
        values.append(("flag", node.flag))
    lines = ["---"]
    lines.extend(f"{key}: {json.dumps(value, ensure_ascii=False)}" for key, value in values)
    lines.append("---")
    return "\n".join(lines)


def note_to_markdown(node: Node) -> str:
    body = node.content.rstrip()
    front = note_front_matter(node)
    return f"{front}\n\n{body}\n" if body else f"{front}\n"


def export_note_markdown(vault: Vault, node_id: int, destination: str | Path) -> Path:
    node = vault.get_node(node_id)
    if node is None:
        raise ValueError("Note does not exist")
    if node.is_folder:
        raise ValueError("Folders cannot be exported as a single Markdown note")
    target = _ensure_suffix(Path(destination), ".md")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(note_to_markdown(node), encoding="utf-8", newline="\n")
    return target


def export_note_html(vault: Vault, node_id: int, destination: str | Path) -> Path:
    node = vault.get_node(node_id)
    if node is None:
        raise ValueError("Note does not exist")
    if node.is_folder:
        raise ValueError("Folders cannot be exported as a single HTML note")
    target = _ensure_suffix(Path(destination), ".html")
    target.parent.mkdir(parents=True, exist_ok=True)
    meta = [
        ("Target", node.target),
        ("Status", node.status_label),
        ("Difficulty", node.difficulty_label if node.difficulty else ""),
        ("Tags", ", ".join(node.tag_list)),
        ("Flag", node.flag),
        ("Updated", node.updated_at),
    ]
    path = vault.path_of(node.id, include_self=False)
    document = render_html(
        node.content,
        node.title,
        subtitle=path or "RedScribe note",
        meta=meta,
    )
    target.write_text(document, encoding="utf-8", newline="\n")
    return target


def export_vault_markdown(vault: Vault, destination: str | Path) -> int:
    """Mirror the vault tree into a folder of Markdown files."""
    target = Path(destination)
    target.mkdir(parents=True, exist_ok=True)
    groups = _group_nodes(vault)
    count = 0

    def walk(parent_id: int | None, directory: Path) -> None:
        nonlocal count
        used: set[str] = set()
        for node in groups.get(parent_id, []):
            if node.is_folder:
                folder_name = _unique_name(
                    safe_filename(node.title, fallback=f"folder-{node.id}"), used
                )
                folder = directory / folder_name
                folder.mkdir(parents=True, exist_ok=True)
                walk(node.id, folder)
            else:
                file_name = _unique_name(
                    safe_filename(node.title, fallback=f"note-{node.id}", extension=".md"), used
                )
                (directory / file_name).write_text(
                    note_to_markdown(node), encoding="utf-8", newline="\n"
                )
                count += 1

    walk(None, target)
    return count


def export_vault_html(vault: Vault, destination: str | Path) -> int:
    """Create a single-file, searchable HTML report of the entire vault."""
    target = _ensure_suffix(Path(destination), ".html")
    target.parent.mkdir(parents=True, exist_ok=True)
    document = vault_report_text(vault)
    target.write_text(document, encoding="utf-8", newline="\n")
    return len(_report_notes(vault))


def vault_report_text(vault: Vault) -> str:
    """Render the whole vault as a standalone HTML report string."""
    groups = _group_nodes(vault)
    stats = vault.stats()
    ordered: list[tuple[Node, int]] = []

    def collect(parent_id: int | None, depth: int) -> None:
        for node in groups.get(parent_id, []):
            ordered.append((node, depth))
            if node.is_folder:
                collect(node.id, depth + 1)

    collect(None, 0)
    notes = [(node, depth) for node, depth in ordered if node.is_note]
    nav: list[str] = []
    for node, depth in ordered:
        indent = 10 + depth * 14
        if node.is_folder:
            nav.append(
                f'<div class="nav-folder" style="padding-left:{indent}px">'
                f"{html.escape(node.title)}</div>"
            )
        else:
            path = vault.path_of(node.id, include_self=False)
            search = _search_blob(node, path)
            nav.append(
                f'<a class="nav-note" href="#note-{node.id}" '
                f'data-search="{html.escape(search, quote=True)}" '
                f'style="margin-left:{indent - 10}px">{html.escape(node.title)}</a>'
            )
    if not nav:
        nav.append('<div class="nav-empty">No notes yet.</div>')
    nav.append('<div id="vault-no-results" class="nav-empty" hidden>No matching notes.</div>')

    sections: list[str] = []
    for node, _depth in notes:
        path = vault.path_of(node.id, include_self=False)
        chips: list[str] = []
        if node.status:
            chips.append(
                f'<span class="chip status-{html.escape(node.status)}">'
                f"{html.escape(node.status_label)}</span>"
            )
        if node.difficulty:
            chips.append(f'<span class="chip">{html.escape(node.difficulty_label)}</span>')
        if node.target:
            chips.append(f'<span class="chip">target: {html.escape(node.target)}</span>')
        for tag in node.tag_list:
            chips.append(f'<span class="chip">#{html.escape(tag)}</span>')
        if node.flag:
            chips.append(f'<span class="chip flag">{html.escape(node.flag)}</span>')
        body = (
            render_markdown_body(node.content)
            if node.content.strip()
            else ('<p class="note-empty">This note is empty.</p>')
        )
        title_html = (
            ""
            if node.content.lstrip().startswith("# ")
            else f'<h2 class="note-title">{html.escape(node.title)}</h2>'
        )
        sections.append(
            f'<section class="note" id="note-{node.id}" '
            f'data-search="{html.escape(_search_blob(node, path), quote=True)}">'
            f'<div class="note-kicker">{html.escape(path or "Vault root")}</div>'
            f"{title_html}"
            f'<div class="note-meta">{"".join(chips)}</div>'
            f'<div class="markdown">{body}</div>'
            f"</section>"
        )

    vault_name = vault.path.stem if vault.path is not None else "RedScribe"
    generated = datetime.now(timezone.utc).date().isoformat()
    summary = (
        f"{stats.notes} notes · {stats.folders} folders · {stats.flags} flags · "
        f"{stats.targets} targets"
    )
    document = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(vault_name)} — RedScribe vault</title>
<style>
{DOCUMENT_CSS}
{_VAULT_CSS}
</style>
</head>
<body>
<div class="vault-layout">
<nav class="vault-nav">
  <div class="vault-brand">REDSCRIBE VAULT</div>
  <div class="vault-title">{html.escape(vault_name)}</div>
  <div class="vault-sub">{html.escape(summary)}</div>
  <input id="vault-search" class="vault-search" type="search" placeholder="Filter notes…">
  {"".join(nav)}
</nav>
<main class="vault-main">
  <header class="report-header">
    <div class="report-kicker">VAULT REPORT · {generated}</div>
    <h1 class="report-title">{html.escape(vault_name)}</h1>
    <div class="report-summary">{html.escape(summary)}</div>
  </header>
  {"".join(sections) if sections else '<p class="note-empty">No notes to report yet.</p>'}
  <footer class="vault-footer">Generated by RedScribe · local-first security notes</footer>
</main>
</div>
<script>
const vaultSearch = document.getElementById('vault-search');
if (vaultSearch) {{
  vaultSearch.addEventListener('input', () => {{
    const query = vaultSearch.value.trim().toLowerCase();
    let visible = 0;
    document.querySelectorAll('.note').forEach((note) => {{
      const match = !query || note.dataset.search.includes(query);
      note.style.display = match ? '' : 'none';
      if (match) visible += 1;
    }});
    document.querySelectorAll('.nav-note').forEach((link) => {{
      link.style.display = !query || link.dataset.search.includes(query) ? '' : 'none';
    }});
    const empty = document.getElementById('vault-no-results');
    if (empty) empty.hidden = !query || visible > 0;
  }});
}}
</script>
</body>
</html>
"""
    return document


def _report_notes(vault: Vault) -> list[Node]:
    return [node for nodes in _group_nodes(vault).values() for node in nodes if node.is_note]


def _search_blob(node: Node, path: str) -> str:
    values = [
        node.title,
        path,
        node.tags,
        node.target,
        node.status,
        node.status_label,
        node.difficulty,
        node.difficulty_label if node.difficulty else "",
    ]
    return " ".join(value for value in values if value).lower()


def _group_nodes(vault: Vault) -> dict[int | None, list[Node]]:
    groups: dict[int | None, list[Node]] = defaultdict(list)
    for node in vault.live_nodes():
        groups[node.parent_id].append(node)
    for nodes in groups.values():
        nodes.sort(key=lambda node: (node.sort_order, node.title.casefold()))
    return groups


def _unique_name(name: str, used: set[str]) -> str:
    candidate = name
    counter = 2
    suffix = Path(name).suffix
    stem = name[: -len(suffix)] if suffix else name
    while candidate.casefold() in used:
        candidate = f"{stem} ({counter}){suffix}"
        counter += 1
    used.add(candidate.casefold())
    return candidate


def _ensure_suffix(path: Path, suffix: str) -> Path:
    if path.suffix.lower() == suffix:
        return path
    if path.suffix:
        return path.with_suffix(suffix)
    return path.with_name(path.name + suffix)
