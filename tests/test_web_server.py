from __future__ import annotations

from redscribe.ui.web.server import static_asset_bytes, static_asset_exists


def test_nested_frontend_assets_are_packaged() -> None:
    assert static_asset_exists("index.html")
    assert static_asset_exists("assets/app.js")
    assert static_asset_exists("assets/app.css")
    assert static_asset_exists("favicon.svg")
    assert static_asset_exists("manifest.webmanifest")
    assert static_asset_bytes("assets/app.js")


def test_static_paths_cannot_escape_the_bundle() -> None:
    assert not static_asset_exists("../server.py")
    assert not static_asset_exists("assets/../../server.py")
    assert not static_asset_exists("/etc/passwd")
    assert static_asset_bytes("../server.py") is None
