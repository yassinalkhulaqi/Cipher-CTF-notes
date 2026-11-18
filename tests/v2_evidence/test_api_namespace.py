from __future__ import annotations

import json
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from http.client import HTTPConnection
from pathlib import Path
from typing import Any

import pytest

from redscribe.storage import db as db_module
from redscribe.storage.db import Vault
from redscribe.ui.web.api import Api
from redscribe.ui.web.server import ApiServer
from redscribe.ui.web.v2.router import V2Router
from redscribe.ui.web.v2.routes import ApiV2
from redscribe.v2.evidence.hashing import encode_base64_payload


def request(
    port: int,
    method: str,
    path: str,
    *,
    body: dict[str, object] | bytes | None = None,
    headers: dict[str, str] | None = None,
) -> tuple[int, dict[str, str], bytes]:
    connection = HTTPConnection("127.0.0.1", port, timeout=5)
    request_headers = dict(headers or {})
    if method == "POST" and "Content-Type" not in request_headers:
        request_headers["Content-Type"] = "application/json"
    payload: bytes | None
    if isinstance(body, dict):
        payload = json.dumps(body).encode("utf-8")
    elif isinstance(body, bytes):
        payload = body
    else:
        payload = None
    connection.request(method, path, body=payload, headers=request_headers)
    response = connection.getresponse()
    status = response.status
    response_headers = dict(response.getheaders())
    data = response.read()
    connection.close()
    return status, response_headers, data


@contextmanager
def running(server: ApiServer) -> Iterator[int]:
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.bound_port
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


@pytest.fixture
def server(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[tuple[int, Vault, Api]]:
    real_connect = db_module.sqlite3.connect

    def connect(*args: Any, **kwargs: Any) -> Any:
        kwargs["check_same_thread"] = False
        return real_connect(*args, **kwargs)

    monkeypatch.setattr(db_module.sqlite3, "connect", connect)
    vault = Vault(tmp_path / "evidence-api.db")
    api = Api(vault)
    try:
        with running(ApiServer(("127.0.0.1", 0), api.handle)) as port:
            yield port, vault, api
    finally:
        vault.close()


def ingest(router: V2Router, filename: str = "sample.txt", data: bytes = b"sample payload") -> str:
    result = router.dispatch(
        "evidence.ingest",
        {"content_base64": encode_base64_payload(data), "filename": filename},
        request_id="ingest-test",
    )
    assert result["ok"], result["error"]
    return str(result["data"]["id"])


def test_namespace_routes_are_registered_on_every_api(vault: Vault) -> None:
    first = ApiV2(vault)
    second = ApiV2(vault)
    evidence_routes = [name for name in first.routes if name.startswith("evidence.")]
    assert len(evidence_routes) == 35
    assert evidence_routes == [name for name in second.routes if name.startswith("evidence.")]
    schema = first.invoke("system.api_schema", {}).data
    assert "evidence.list" in schema["route_names"]
    capabilities = first.invoke("system.capabilities", {}).data
    assert "evidence" in capabilities["namespaces"]


def test_router_ingest_list_detail_and_verify(vault: Vault) -> None:
    router = V2Router(vault)
    evidence_id = ingest(router)
    listing = router.dispatch("evidence.list", {"limit": 10}, request_id="list")
    assert listing["ok"]
    assert len(listing["data"]) == 1
    assert listing["data"][0]["id"] == evidence_id
    detail = router.dispatch("evidence.detail", {"id": evidence_id}, request_id="detail")
    assert detail["ok"]
    assert detail["data"]["record"]["id"] == evidence_id
    assert "integrity" in detail["data"]
    report = router.dispatch("evidence.verify", {"id": evidence_id}, request_id="verify")
    assert report["ok"]
    assert report["data"]["state"] == "verified"
    summary = router.dispatch("evidence.verify_all", {}, request_id="verify-all")
    assert summary["data"]["summary"]["total"] >= 1
    stats = router.dispatch("evidence.stats", {}, request_id="stats")
    assert stats["data"]["total"] == 1
    search = router.dispatch("evidence.search", {"query": "sample"}, request_id="search")
    assert len(search["data"]) == 1


def test_router_hash_thumbnail_and_manifest_routes(vault: Vault) -> None:
    router = V2Router(vault)
    payload = encode_base64_payload(b"manifest body")
    digest = router.dispatch("evidence.hash", {"content_base64": payload}, request_id="hash")
    assert digest["ok"]
    assert len(digest["data"]["sha256"]) == 64
    thumbnail = router.dispatch(
        "evidence.thumbnail",
        {"content_base64": payload, "filename": "report.txt"},
        request_id="thumb",
    )
    assert thumbnail["ok"]
    assert thumbnail["data"]["mime"]["mime_type"] == "text/plain"
    evidence_id = ingest(router, filename="report.txt", data=b"manifest body")
    exported = router.dispatch("evidence.manifest.export", {}, request_id="export")
    assert exported["ok"]
    assert any(item["evidence_id"] == evidence_id for item in exported["data"]["entries"])
    preview = router.dispatch(
        "evidence.manifest.preview", {"manifest": exported["data"]}, request_id="preview"
    )
    assert preview["ok"]
    assert preview["data"]["valid"]
    bundle = router.dispatch("evidence.manifest.bundle", {}, request_id="bundle")
    assert encode_base64_payload(b"manifest body") in bundle["data"]["files"].values()


def test_router_custody_links_retention_and_provenance(vault: Vault) -> None:
    router = V2Router(vault)
    evidence_id = ingest(router)
    custody = router.dispatch("evidence.custody.list", {"id": evidence_id}, request_id="custody")
    assert custody["data"]["valid"]
    added = router.dispatch(
        "evidence.custody.add",
        {
            "id": evidence_id,
            "action": "transferred",
            "actor": "alice",
            "description": "Sent to lab",
        },
        request_id="custody-add",
    )
    assert added["ok"]
    verified = router.dispatch(
        "evidence.custody.verify", {"id": evidence_id}, request_id="custody-verify"
    )
    assert verified["data"]["valid"]
    link = router.dispatch(
        "evidence.links.add",
        {"id": evidence_id, "finding_id": "F-9", "link_type": "supports"},
        request_id="link-add",
    )
    assert link["ok"]
    link_id = link["data"]["id"]
    links = router.dispatch("evidence.links.view", {"finding_id": "f-9"}, request_id="links-view")
    assert links["data"]["summary"]["total"] == 1
    assert router.dispatch("evidence.links.remove", {"link_id": link_id}, request_id="link-remove")[
        "ok"
    ]
    retention = router.dispatch(
        "evidence.retention.set",
        {"id": evidence_id, "retain_days": 30},
        request_id="retention-set",
    )
    assert retention["data"]["retain_days"] == 30
    hold = router.dispatch(
        "evidence.retention.hold",
        {"id": evidence_id, "held": True, "reason": "Litigation"},
        request_id="retention-hold",
    )
    assert hold["data"]["legal_hold"]
    plan = router.dispatch("evidence.retention.plan", {}, request_id="retention-plan")
    assert len(plan["data"]) == 1
    applied = router.dispatch("evidence.retention.apply", {}, request_id="retention-apply")
    assert len(applied["data"]["decisions"]) == 1
    provenance = router.dispatch(
        "evidence.provenance.update",
        {"id": evidence_id, "operator": "bob", "case_reference": "CASE-9"},
        request_id="provenance-update",
    )
    assert provenance["data"]["summary"]["operator"] == "bob"


def test_router_reports_schema_violations_and_not_found(vault: Vault) -> None:
    router = V2Router(vault)
    missing = router.dispatch("evidence.get", {}, request_id="missing")
    assert not missing["ok"]
    assert missing["error"]["code"] == "evidence_validation_error"
    unknown = router.dispatch("evidence.get", {"id": "ev_missing001"}, request_id="unknown")
    assert not unknown["ok"]
    assert unknown["error"]["code"] == "evidence_not_found"


def test_http_evidence_ingest_and_capabilities(server: tuple[int, Vault, Api]) -> None:
    port, _, _ = server
    status, _, raw = request(port, "POST", "/api/v2/system/capabilities", body={})
    assert status == 200
    assert "evidence" in json.loads(raw)["data"]["namespaces"]
    status, _, raw = request(
        port,
        "POST",
        "/api/v2/evidence/ingest",
        body={"content_base64": encode_base64_payload(b"http evidence"), "filename": "http.txt"},
    )
    assert status == 200
    envelope = json.loads(raw)
    assert envelope["ok"]
    evidence_id = envelope["data"]["id"]
    status, _, raw = request(port, "POST", "/api/v2/evidence/get", body={"id": evidence_id})
    assert status == 200
    assert json.loads(raw)["data"]["id"] == evidence_id
    status, _, raw = request(
        port,
        "POST",
        "/api/v2/evidence/ingest",
        body={"content_base64": "bad base64", "filename": "bad.txt"},
    )
    assert status == 400
    assert json.loads(raw)["ok"] is False
