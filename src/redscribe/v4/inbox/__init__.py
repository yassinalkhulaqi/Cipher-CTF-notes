"""Universal capture inbox for RedScribe v4.

This package provides one pipeline for text captured from notes, links, code
snippets, flag tokens, and clipboard pastes. It exposes immutable records, a
deterministic parser, strict templates, a closed triage state machine, an
indexed store, and v4 API handlers. Importing the package has no side effects;
``register(api)`` wires routes into a :class:`~redscribe.v4.api_v4.RouteRegistry`.
"""

from __future__ import annotations

from redscribe.v4.inbox.api import InboxRoutes, register
from redscribe.v4.inbox.service import (
    ACTIONS,
    DEFAULT_TEMPLATES,
    TRANSITIONS,
    CaptureNotFoundError,
    CaptureParser,
    CaptureResult,
    InboxService,
    MissingTemplateKeyError,
    TemplateEngine,
    TemplateError,
    TransitionError,
    TriageMachine,
    UnknownTemplateError,
)
from redscribe.v4.inbox.storage import (
    DuplicateItemError,
    InboxImportError,
    InboxStore,
    StorageError,
)
from redscribe.v4.inbox.types import (
    CaptureDraft,
    CaptureItem,
    CaptureSource,
    TriageState,
    compute_content_hash,
    normalize_raw,
    normalize_tags,
)

__all__ = [
    "ACTIONS",
    "DEFAULT_TEMPLATES",
    "TRANSITIONS",
    "CaptureDraft",
    "CaptureItem",
    "CaptureNotFoundError",
    "CaptureParser",
    "CaptureResult",
    "CaptureSource",
    "DuplicateItemError",
    "InboxImportError",
    "InboxRoutes",
    "InboxService",
    "InboxStore",
    "MissingTemplateKeyError",
    "StorageError",
    "TemplateEngine",
    "TemplateError",
    "TransitionError",
    "TriageMachine",
    "TriageState",
    "UnknownTemplateError",
    "compute_content_hash",
    "normalize_raw",
    "normalize_tags",
    "register",
]
