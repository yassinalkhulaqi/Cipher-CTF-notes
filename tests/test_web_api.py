from __future__ import annotations

from typing import Any

import pytest

from redscribe.storage.db import Vault
from redscribe.ui.web.api import Api, ApiError, WebOverrides


def test_api_covers_core_routes(vault: Vault) -> None:
    api = Api(vault, WebOverrides(theme="light", font_size=15))

    boot = api.handle("boot", {})
    assert boot["theme"] == "light"
    assert boot["font_size"] == 15
    assert api.handle("tree", {}) == []
    assert api.handle("templates", {})
    assert api.handle("flag_patterns", {})

    folder = api.handle("create_folder", {"title": "Web"})
    note = api.handle(
        "create_note",
        {
            "title": "SAML",
            "template_key": "ctf",
            "parent_id": folder["id"],
            "target": "example.com",
        },
    )
    assert api.handle("node", {"id": folder["id"]})["children"]
    assert api.handle("node", {"id": note["id"]})["content"]

    api.handle(
        "update_node",
        {
            "id": note["id"],
            "tags": "web, saml",
            "status": "active",
            "difficulty": "medium",
            "flag": "flag{x}",
            "target": "target.tld",
        },
    )
    api.handle("save_content", {"id": note["id"], "content": "# body\n[link](missing)"})
    api.handle("set_pinned", {"id": note["id"], "pinned": True})
    assert api.handle("pinned_notes", {})
    assert api.handle("recent_notes", {"limit": 5})
    assert api.handle("stats", {})
    assert api.handle("search", {"query": "body"})
    assert api.handle("quick_jump", {"query": "SAML"})
    assert api.handle("render_preview", {"content": "# hi"})["html"]
    assert api.handle("graph", {})["nodes"]
    assert api.handle("backlinks", {"id": note["id"]})
    assert api.handle("timeline", {"folder_id": folder["id"], "limit": 5})
    assert api.handle("tag_counts", {})
    assert api.handle("notes_tagged", {"tag": "web"})
    assert api.handle("collected_flags", {})
    assert api.handle("flag_insights", {})

    assert api.handle("list_snippets", {})
    assert api.handle("search_snippets", {"query": "curl"})
    assert api.handle("resolve_snippet", {"command": "curl {{target}}", "target": "x"})
    snippet = api.handle(
        "create_snippet",
        {"title": "Mine", "command": "echo {{target}}", "description": "d", "tags": "x"},
    )
    api.handle("update_snippet", {**snippet, "title": "Renamed"})
    api.handle("delete_snippet", {"id": snippet["id"]})

    assert api.handle("export_note_markdown", {"id": note["id"]})["mime"] == "text/markdown"
    assert api.handle("export_note_html", {"id": note["id"]})["mime"] == "text/html"
    assert api.handle("export_vault_html", {})["filename"]
    assert api.handle("backup_vault", {})["filename"]
    assert api.handle("rebuild_search_index", {}) == {"rebuilt": True}
    assert api.handle("quick_capture", {"content": "captured line"})["title"] == "captured line"

    versions = api.handle("list_versions", {"id": note["id"]})
    assert versions
    assert api.handle("get_version", {"version_id": versions[0]["id"]})
    assert api.handle("restore_version", {"version_id": versions[0]["id"]})

    api.handle(
        "set_settings",
        {
            "theme": "dark",
            "font_size": 14,
            "view_mode": "preview",
            "last_template": "blank",
            "last_note": note["id"],
            "sidebar_width": 300,
            "split_sash": 50,
            "tree_expanded": str(folder["id"]),
            "restore_last_note": True,
            "sync_preview_scroll": "off",
        },
    )
    assert api.handle("get_settings", {})["theme"] == "dark"

    duplicate = api.handle("duplicate_node", {"id": note["id"]})
    api.handle("reorder_node", {"id": duplicate["id"], "offset": -1})
    api.handle("move_node", {"id": duplicate["id"], "parent_id": folder["id"]})
    assert api.handle("trash_node", {"id": duplicate["id"]}) == {"removed": 1}
    assert api.handle("trashed_nodes", {})
    assert api.handle("restore_node", {"id": duplicate["id"]})
    assert api.handle("empty_trash", {})["removed"] == 0


@pytest.mark.parametrize(
    ("method", "body"),
    [
        ("missing", {}),
        ("create_folder", {"title": "x" * 201}),
        ("node", {}),
        ("create_note", {"title": "x" * 201}),
        ("rename", {"id": 1, "title": " "}),
        ("update_node", {"id": 1, "status": "nope"}),
        ("update_node", {"id": 1, "difficulty": "nope"}),
        ("update_node", {"id": 1}),
        ("save_content", {"id": 1, "content": 5}),
        ("set_pinned", {"id": 1, "pinned": "yes"}),
        ("quick_jump", {"query": 5}),
        ("notes_tagged", {}),
        ("backlinks", {"id": "x"}),
        ("search_snippets", {}),
        ("create_snippet", {"title": "x", "command": "y", "tags": "z" * 501}),
        ("delete_snippet", {"id": 999}),
        ("render_preview", {}),
        ("set_settings", {"unknown": 1}),
        ("set_settings", {"font_size": 99}),
        ("set_settings", {"theme": "blue"}),
        ("set_settings", {"view_mode": "wide"}),
        ("set_settings", {"last_template": "nope"}),
        ("set_settings", {"tree_expanded": "abc"}),
        ("export_note_markdown", {"id": 999}),
        ("get_version", {"version_id": 999}),
    ],
)
def test_api_rejects_bad_requests(vault: Vault, method: str, body: dict[str, Any]) -> None:
    api = Api(vault)
    with pytest.raises(ApiError):
        api.handle(method, body)


def test_api_reports_missing_nodes(vault: Vault) -> None:
    api = Api(vault)
    with pytest.raises(ApiError) as error:
        api.handle("node", {"id": 999})
    assert error.value.status == 404
