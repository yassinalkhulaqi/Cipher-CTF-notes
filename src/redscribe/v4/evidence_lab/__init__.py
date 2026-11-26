"""Evidence Lab — v4 evidence metadata inspection slice.

The package exposes typed value objects, pure inspection services, an indexed
store, and v4 API handlers. Importing the package has no side effects; route
registration happens only through :func:`register`.
"""

from __future__ import annotations

from .api import (
    EvidenceApi,
    EvidenceRequest,
    handle_get,
    handle_post,
)
from .api import (
    register as register_api,
)
from .service import (
    BundleDiffer,
    CustodyGraph,
    HashVerifier,
    HexDumper,
    InspectionPipeline,
    StringExtractor,
)
from .storage import EvidenceStore
from .types import (
    ChainVerification,
    CustodyAction,
    CustodyEntry,
    EvidenceRecord,
    HashAlgorithm,
    HashVerification,
    HexCell,
    HexRow,
    InspectionResult,
    StringEncoding,
    StringHit,
)

__all__ = [
    "BundleDiffer",
    "ChainVerification",
    "CustodyAction",
    "CustodyEntry",
    "CustodyGraph",
    "EvidenceApi",
    "EvidenceRecord",
    "EvidenceRequest",
    "EvidenceStore",
    "HashAlgorithm",
    "HashVerification",
    "HashVerifier",
    "HexCell",
    "HexDumper",
    "HexRow",
    "InspectionPipeline",
    "InspectionResult",
    "StringEncoding",
    "StringExtractor",
    "StringHit",
    "handle_get",
    "handle_post",
    "register",
]


def register(api: object) -> None:
    """Register this feature's GET and POST routes on ``api``."""
    register_api(api)
