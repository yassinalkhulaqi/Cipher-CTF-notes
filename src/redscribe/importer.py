"""Backward-compatible imports for the canonical import service.

New code should import from :mod:`redscribe.services.importer`.
"""

from __future__ import annotations

from redscribe.services.importer import (
    import_directory,
    import_markdown_file,
    import_markdown_files,
    normalize_tags,
    parse_front_matter,
    read_text_file,
    title_from_body,
)

__all__ = [
    "import_directory",
    "import_markdown_file",
    "import_markdown_files",
    "normalize_tags",
    "parse_front_matter",
    "read_text_file",
    "title_from_body",
]
