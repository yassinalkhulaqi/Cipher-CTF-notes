"""Extensions namespace: declarative manifest and capability routes."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from redscribe.v3.api.envelope import PageMeta, success
from redscribe.v3.api.errors import V3Error, V3ErrorCode
from redscribe.v3.api.pagination import PageRequest
from redscribe.v3.api.request_id import normalize_request_id, require_str
from redscribe.v3.api.router import V3Router
from redscribe.v3.api_sdk.service import get_service


def _header(headers: Mapping[str, str], name: str) -> str:
    target = name.casefold()
    for key, value in headers.items():
        if key.casefold() == target:
            return value
    return ""


def _ok(
    body: Mapping[str, Any],
    headers: Mapping[str, str],
    data: Any,
    *,
    etag: str = "",
    page: PageMeta | None = None,
) -> dict[str, Any]:
    return success(
        data,
        request_id=normalize_request_id(_header(headers, "X-Request-ID")),
        etag=etag,
        page=page,
    ).as_dict()


def _write_opt_in(body: Mapping[str, Any], headers: Mapping[str, str]) -> bool:
    flag = body.get("allow_write", False)
    header = _header(headers, "X-Allow-Write").casefold()
    return flag is True or header in {"1", "true", "yes"}


def _as_page(data: dict[str, Any]) -> PageMeta:
    raw = data.get("page", {})
    return PageMeta(
        page=int(raw.get("page", 1)),
        page_size=int(raw.get("page_size", 50)),
        total=int(raw.get("total", 0)),
        has_next=raw.get("has_next") is True,
        has_previous=raw.get("has_previous") is True,
    )


def register(router: V3Router) -> None:
    """Register every extensions route on the supplied router."""

    def validate(body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        document = body.get("manifest", body)
        return _ok(body, headers, get_service().validate(document))

    def schema(body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        return _ok(body, headers, get_service().schema())

    def example(body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        return _ok(body, headers, get_service().example())

    def contracts(body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        return _ok(body, headers, get_service().contracts())

    def safety(body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        return _ok(body, headers, get_service().safety())

    def health(body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        return _ok(body, headers, get_service().health())

    def capabilities(body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        required = body.get("required", ())
        if not isinstance(required, (list, tuple)):
            raise V3Error(V3ErrorCode.INVALID_TYPE, "'required' must be a list", field="required")
        data = get_service().negotiate(str(item) for item in required)
        return _ok(body, headers, data)

    def list_manifests(body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        page = PageRequest.parse(
            offset=body.get("offset"),
            size=body.get("size"),
            cursor=str(body.get("cursor", "")),
        )
        data = get_service().list(offset=page.offset, size=page.size)
        return _ok(body, headers, data, page=_as_page(data))

    def get_manifest(body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        identifier = require_str(body, "id", limit=120)
        data = get_service().get(identifier, etag=_header(headers, "If-None-Match"))
        return _ok(body, headers, data, etag=str(data.get("etag", "")))

    def install_manifest(body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        document = body.get("manifest")
        if not isinstance(document, Mapping):
            raise V3Error(
                V3ErrorCode.INVALID_TYPE, "'manifest' must be an object", field="manifest"
            )
        data = get_service().install(
            document,
            allow_write=_write_opt_in(body, headers),
            expected_etag=_header(headers, "If-None-Match"),
        )
        return _ok(body, headers, data, etag=str(data.get("etag", "")))

    def remove_manifest(body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        identifier = require_str(body, "id", limit=120)
        data = get_service().remove(
            identifier,
            allow_write=_write_opt_in(body, headers),
            expected_etag=_header(headers, "If-None-Match"),
        )
        return _ok(body, headers, data)

    def routes(body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        return _ok(body, headers, router.manifest())

    router.add("extensions", "validate", validate, public=True)
    router.add("extensions", "schema", schema, public=True)
    router.add("extensions", "example", example, public=True)
    router.add("extensions", "contracts", contracts, public=True)
    router.add("extensions", "safety", safety, public=True)
    router.add("extensions", "health", health, public=True)
    router.add("extensions", "capabilities", capabilities, public=True)
    router.add("extensions", "list", list_manifests, public=True)
    router.add("extensions", "get", get_manifest, public=True)
    router.add("extensions", "install", install_manifest)
    router.add("extensions", "remove", remove_manifest)
    router.add("extensions", "routes", routes, public=True)
