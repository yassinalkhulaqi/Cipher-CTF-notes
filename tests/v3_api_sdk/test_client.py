"""SDK client behavior: envelopes, errors, ETag, idempotency, and history."""

from __future__ import annotations

import pytest

from redscribe.v3.api.router import V3Router
from redscribe.v3.api_sdk.capabilities import CapabilityNegotiator
from redscribe.v3.api_sdk.client import SdkClient
from redscribe.v3.api_sdk.envelopes import decode_envelope, render_envelope
from redscribe.v3.api_sdk.errors import (
    CapabilityDeniedError,
    ReadOnlyViolationError,
    SdkError,
)
from redscribe.v3.api_sdk.transport import InProcessTransport
from redscribe.v3.capabilities import CAP_EXTENSIONS, Capabilities
from redscribe.v3.config import V3Config


def test_client_call_returns_typed_envelope(client: SdkClient) -> None:
    response = client.call("system", "info", {"echo": "hello"})
    assert response.ok
    assert response.namespace == "system"
    assert response.action == "info"
    assert response.api_version == "3.0"
    assert response.request_id.startswith("req_")
    assert response.data["schema_version"] == 5
    assert client.history.size() == 1
    record = client.history.last()
    assert record is not None
    assert record.body_keys == ("echo",)
    assert record.status == 200
    assert not record.failed


def test_client_data_and_envelope_helpers(client: SdkClient) -> None:
    schema = client.data("extensions", "schema")
    assert schema["schema_id"] == "redscribe-extension/1"
    envelope = client.envelope("extensions", "health")
    assert "data" in envelope
    assert envelope["meta"]["api_version"] == "3.0"
    assert client.data("extensions", "example")["id"] == "example.panel"


def test_client_raises_on_error_and_can_tolerate_errors(client: SdkClient) -> None:
    with pytest.raises(SdkError) as excinfo:
        client.call("extensions", "get", {})
    assert excinfo.value.code == "invalid_type"
    assert excinfo.value.field == "id"
    failed = client.call("extensions", "get", {}, allow_errors=True)
    assert not failed.ok
    rendered = render_envelope(failed)
    assert rendered["error"]["code"] == "invalid_type"
    assert rendered["meta"]["request_id"].startswith("req_")


def test_client_reports_unknown_route(client: SdkClient) -> None:
    with pytest.raises(SdkError) as excinfo:
        client.call("extensions", "does_not_exist")
    assert excinfo.value.code == "unknown_route"
    assert excinfo.value.status == 404


def test_client_capability_denial(router: V3Router) -> None:
    transport = InProcessTransport(
        router=router,
        negotiator=CapabilityNegotiator(capabilities=Capabilities(enabled=frozenset())),
    )
    client = SdkClient(transport=transport)
    with pytest.raises(CapabilityDeniedError) as excinfo:
        client.call("system", "info", capability="findings")
    assert excinfo.value.status == 403
    assert excinfo.value.context["capability"] == "findings"
    assert client.history.last().error_code == "forbidden"  # type: ignore[union-attr]


def test_client_write_is_read_only_by_default(
    client: SdkClient, sample_manifest: dict[str, object]
) -> None:
    with pytest.raises(ReadOnlyViolationError) as excinfo:
        client.call(
            "extensions",
            "install",
            {"manifest": sample_manifest, "allow_write": True},
        )
    assert excinfo.value.code == "read_only_violation"
    assert excinfo.value.field == "allow_write"
    assert client.history.last().route == "/api/v3/extensions/install"  # type: ignore[union-attr]


def test_client_conditional_etag_returns_not_modified(
    client: SdkClient,
    writable_service: object,
    sample_manifest: dict[str, object],
) -> None:
    from redscribe.v3.api_sdk.manifest import parse_manifest
    from redscribe.v3.api_sdk.service import ExtensionService

    assert isinstance(writable_service, ExtensionService)
    writable_service.store.install(parse_manifest(sample_manifest))
    first = client.call("extensions", "get", {"id": sample_manifest["id"]})
    assert first.ok
    assert first.etag
    second = client.call("extensions", "get", {"id": sample_manifest["id"]}, etag=first.etag)
    assert second.status == 304
    assert second.not_modified
    assert second.data is None
    assert second.etag == first.etag


def test_client_idempotency_reuses_cached_result(
    writable_client: SdkClient, sample_manifest: dict[str, object]
) -> None:
    body = {"manifest": sample_manifest, "allow_write": True}
    first = writable_client.call("extensions", "install", body, idempotency_key="install-once")
    second = writable_client.call("extensions", "install", body, idempotency_key="install-once")
    assert first.ok
    assert second.ok
    assert not first.cached
    assert second.cached
    assert second.data == first.data
    with pytest.raises(SdkError) as excinfo:
        writable_client.call(
            "extensions",
            "install",
            {**body, "manifest": {**sample_manifest, "title": "Changed"}},
            idempotency_key="install-once",
        )
    assert excinfo.value.code == "idempotency_conflict"


def test_client_install_and_remove_with_opt_in(
    writable_client: SdkClient, sample_manifest: dict[str, object]
) -> None:
    installed = writable_client.call(
        "extensions", "install", {"manifest": sample_manifest, "allow_write": True}
    )
    assert installed.ok
    assert installed.data["extension"]["id"] == "example.panel"
    removed = writable_client.call(
        "extensions", "remove", {"id": "example.panel", "allow_write": True}
    )
    assert removed.ok
    assert removed.data["removed"] is True


def test_client_service_denies_writes_when_config_disabled(
    router: V3Router, sample_manifest: dict[str, object]
) -> None:
    transport = InProcessTransport(router=router, allow_write=True)
    client = SdkClient(transport=transport)
    with pytest.raises(CapabilityDeniedError) as excinfo:
        client.call(
            "extensions",
            "install",
            {"manifest": sample_manifest, "allow_write": True},
        )
    assert "disabled by local configuration" in excinfo.value.message


def test_client_validates_body_size_and_headers(
    client: SdkClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("redscribe.v3.api_sdk.transport.MAX_BODY_BYTES", 16)
    with pytest.raises(SdkError) as excinfo:
        client.call("system", "info", {"blob": "x" * 100})
    assert excinfo.value.code == "payload_too_large"
    monkeypatch.undo()
    with pytest.raises(SdkError) as header_error:
        client.call(
            "system",
            "info",
            headers={"X-Request-ID": "bad id!"},
        )
    assert header_error.value.code == "invalid_request"


def test_transport_describe_and_default_router() -> None:
    transport = InProcessTransport()
    described = transport.describe()
    assert described["kind"] == "in_process"
    assert described["allow_write"] is False
    assert "extensions.install" in described["write_actions"]
    assert described["route_count"] > 0
    assert "extensions" in described["capabilities"]["advertised"]


def test_decode_envelope_handles_malformed_metadata() -> None:
    response = decode_envelope(
        {"data": 1, "meta": {"page": {"page": "bad"}, "warnings": [1, "ok"]}},
        namespace="x",
        action="y",
    )
    assert response.page is None
    assert response.warnings == ("ok",)
    assert response.data == 1
    error = decode_envelope(
        {"error": {"code": "not_found", "message": "Gone"}},
        namespace="x",
        action="y",
        status=404,
    )
    assert error.code == "not_found"
    assert error.status == 404


def test_allow_write_service_can_be_configured() -> None:
    config = V3Config(allow_extensions=True, enabled_capabilities=(CAP_EXTENSIONS,))
    transport = InProcessTransport(allow_write=True)
    assert transport.allow_write
    assert config.allow_extensions
