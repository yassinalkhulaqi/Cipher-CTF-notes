"""Import Markdown files and folders into a RedScribe vault."""

from __future__ import annotations

import codecs
from pathlib import Path

from redscribe.content.render_frontmatter import (
    normalize_tag_string as _normalize_tag_string,
)
from redscribe.content.render_frontmatter import (
    parse_front_matter as _parse_front_matter,
)
from redscribe.content.render_frontmatter import (
    title_from_body as _title_from_body,
)
from redscribe.domain.models import DIFFICULTIES, STATUSES, Node
from redscribe.storage.db import Vault

_MARKDOWN_SUFFIXES = {".md", ".markdown", ".txt"}
_SKIP_DIRECTORIES = {".git", ".obsidian", ".trash", "node_modules", "__pycache__"}


def read_text_file(path: Path) -> str:
    return _decode_bytes(path.read_bytes())


def parse_front_matter(text: str) -> tuple[dict[str, str], str]:
    """Parse a simple YAML front matter block and return metadata plus body."""
    return _parse_front_matter(text)


def normalize_tags(value: str) -> str:
    return _normalize_tag_string(value)


def title_from_body(body: str, fallback: str) -> str:
    return _title_from_body(body, fallback)


def import_markdown_file(vault: Vault, path: str | Path, parent_id: int | None = None) -> Node:
    """Import one Markdown file as a note."""
    source = Path(path)
    text = read_text_file(source)
    metadata, body = parse_front_matter(text)
    title = metadata.get("title", "").strip() or title_from_body(body, source.stem)
    status = metadata.get("status", "todo").strip().lower()
    if status not in STATUSES:
        status = "todo"
    difficulty = metadata.get("difficulty", "").strip().lower()
    if difficulty not in DIFFICULTIES:
        difficulty = ""
    return vault.create_node(
        title or source.stem or "Imported note",
        parent_id,
        content=body,
        tags=normalize_tags(metadata.get("tags", "")),
        target=metadata.get("target", "").strip(),
        status=status,
        difficulty=difficulty,
        flag=metadata.get("flag", "").strip(),
    )


def import_markdown_files(
    vault: Vault, paths: list[str] | list[Path], parent_id: int | None = None
) -> list[Node]:
    """Import a list of Markdown files, returning the created notes."""
    imported: list[Node] = []
    for raw_path in sorted((Path(item) for item in paths), key=lambda item: item.name.casefold()):
        if raw_path.suffix.lower() not in _MARKDOWN_SUFFIXES:
            continue
        imported.append(import_markdown_file(vault, raw_path, parent_id))
    return imported


def import_directory(
    vault: Vault, directory: str | Path, parent_id: int | None = None
) -> tuple[Node | None, int]:
    """Import a directory tree, mirroring folders into the vault."""
    source = Path(directory)
    if not source.is_dir():
        raise NotADirectoryError(str(source))
    folder = vault.create_node(source.name or "Imported folder", parent_id, kind="folder")
    count = 0
    for child in sorted(source.iterdir(), key=lambda item: (item.is_file(), item.name.casefold())):
        if child.is_symlink():
            continue
        if child.name.startswith(".") or child.name in _SKIP_DIRECTORIES:
            continue
        if child.is_dir():
            _subfolder, child_count = import_directory(vault, child, folder.id)
            count += child_count
        elif child.is_file() and child.suffix.lower() in _MARKDOWN_SUFFIXES:
            import_markdown_file(vault, child, folder.id)
            count += 1
    if count == 0:
        vault.delete_node(folder.id, permanent=True)
        return None, 0
    return folder, count


def _decode_bytes(data: bytes) -> str:
    if data.startswith(codecs.BOM_UTF32_LE):
        return data.decode("utf-32")
    if data.startswith(codecs.BOM_UTF32_BE):
        return data.decode("utf-32")
    if data.startswith(codecs.BOM_UTF16_LE):
        return data.decode("utf-16")
    if data.startswith(codecs.BOM_UTF16_BE):
        return data.decode("utf-16")
    for encoding in ("utf-8-sig", "utf-8", "cp1252"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")
