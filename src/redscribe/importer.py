"""Import Markdown files and folders into a RedScribe vault."""

from __future__ import annotations

import json
import re
from pathlib import Path

from redscribe.db import Vault
from redscribe.domain.models import DIFFICULTIES, STATUSES, Node

_FRONT_MATTER_KEY = re.compile(r"^(?P<key>[A-Za-z0-9_-]+)\s*:\s*(?P<value>.*)$")
_HEADING = re.compile(r"^\s{0,3}#\s+(?P<title>.+?)\s*#*\s*$")
_MARKDOWN_SUFFIXES = {".md", ".markdown", ".txt"}
_SKIP_DIRECTORIES = {".git", ".obsidian", ".trash", "node_modules", "__pycache__"}


def read_text_file(path: Path) -> str:
    data = path.read_bytes()
    for encoding in ("utf-8-sig", "utf-8", "cp1252"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def parse_front_matter(text: str) -> tuple[dict[str, str], str]:
    """Parse a simple YAML front matter block and return metadata plus body."""
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    if not normalized.startswith("---\n"):
        return {}, normalized
    lines = normalized.split("\n")
    end = -1
    for index in range(1, len(lines)):
        if lines[index].strip() in {"---", "..."}:
            end = index
            break
    if end < 0:
        return {}, normalized
    metadata: dict[str, str] = {}
    for line in lines[1:end]:
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        match = _FRONT_MATTER_KEY.match(line)
        if not match:
            continue
        key = match.group("key").strip().lower()
        value = _clean_value(match.group("value").strip())
        if key == "tags":
            value = normalize_tags(value)
        metadata[key] = value
    body = "\n".join(lines[end + 1 :]).lstrip("\n")
    return metadata, body


def _clean_value(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        if value[0] == '"':
            try:
                parsed = json.loads(value)
                if isinstance(parsed, str):
                    return parsed
            except json.JSONDecodeError:
                pass
        return value[1:-1]
    return value


def normalize_tags(value: str) -> str:
    cleaned = value.strip()
    if cleaned.startswith("[") and cleaned.endswith("]"):
        cleaned = cleaned[1:-1]
    return ",".join(part.strip() for part in cleaned.split(",") if part.strip())


def title_from_body(body: str, fallback: str) -> str:
    for line in body.splitlines():
        if not line.strip():
            continue
        match = _HEADING.match(line)
        if match:
            return match.group("title").strip() or fallback
        break
    return fallback


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
        if child.name.startswith(".") or child.name in _SKIP_DIRECTORIES:
            continue
        if child.is_dir():
            _subfolder, child_count = import_directory(vault, child, folder.id)
            count += child_count
        elif child.suffix.lower() in _MARKDOWN_SUFFIXES:
            import_markdown_file(vault, child, folder.id)
            count += 1
    if count == 0:
        vault.delete_node(folder.id, permanent=True)
        return None, 0
    return folder, count
