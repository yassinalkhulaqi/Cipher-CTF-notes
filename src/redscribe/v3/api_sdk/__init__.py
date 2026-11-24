"""API v3 SDK and safe scripting surface for local extensions."""

from __future__ import annotations

from redscribe.v3.api_sdk.capabilities import CapabilityDecision, CapabilityNegotiator
from redscribe.v3.api_sdk.client import SdkClient
from redscribe.v3.api_sdk.envelopes import render_envelope
from redscribe.v3.api_sdk.errors import (
    CapabilityDeniedError,
    ManifestError,
    NotModifiedError,
    ReadOnlyViolationError,
    SafetyViolationError,
    ScriptError,
    SdkError,
)
from redscribe.v3.api_sdk.history import CallLog, CallRecord
from redscribe.v3.api_sdk.manifest import (
    SCHEMA_ID,
    Contribution,
    ExtensionManifest,
    ManifestIssue,
    ValidationReport,
    example_manifest,
    manifest_schema,
    parse_manifest,
    validate_manifest,
)
from redscribe.v3.api_sdk.models import PageResult, SdkRequest, SdkResponse
from redscribe.v3.api_sdk.pagination import collect_pages, iter_pages, next_page_request
from redscribe.v3.api_sdk.safety import (
    SafetyReport,
    assert_no_code_execution,
    audit_sources,
    package_sources,
)
from redscribe.v3.api_sdk.scripting import (
    ScriptPlan,
    ScriptResult,
    ScriptRunner,
    ScriptStep,
    StepOutcome,
    example_script,
)
from redscribe.v3.api_sdk.service import (
    ExtensionService,
    get_service,
    reset_service,
    set_service,
)
from redscribe.v3.api_sdk.transport import InProcessTransport, Transport

SDK_VERSION = "1.0.0"

__all__ = [
    "SCHEMA_ID",
    "SDK_VERSION",
    "CallLog",
    "CallRecord",
    "CapabilityDecision",
    "CapabilityDeniedError",
    "CapabilityNegotiator",
    "Contribution",
    "ExtensionManifest",
    "ExtensionService",
    "InProcessTransport",
    "ManifestError",
    "ManifestIssue",
    "NotModifiedError",
    "PageResult",
    "ReadOnlyViolationError",
    "SafetyReport",
    "SafetyViolationError",
    "ScriptError",
    "ScriptPlan",
    "ScriptResult",
    "ScriptRunner",
    "ScriptStep",
    "SdkClient",
    "SdkError",
    "SdkRequest",
    "SdkResponse",
    "StepOutcome",
    "Transport",
    "ValidationReport",
    "assert_no_code_execution",
    "audit_sources",
    "collect_pages",
    "example_manifest",
    "example_script",
    "get_service",
    "iter_pages",
    "manifest_schema",
    "next_page_request",
    "package_sources",
    "parse_manifest",
    "render_envelope",
    "reset_service",
    "set_service",
    "validate_manifest",
]
