from __future__ import annotations

import pytest

from redscribe.storage.db import Vault
from redscribe.ui.web.api import Api, ApiError


def test_quick_capture_creates_a_note_with_content(vault: Vault) -> None:
    api = Api(vault)

    created = api.quick_capture(
        {
            "title": "Found a weak endpoint",
            "content": "GET /api/user/1 without auth",
            "target": "app.acme.test",
            "tags": "web, idor",
        }
    )

    assert created["title"] == "Found a weak endpoint"
    assert created["target"] == "app.acme.test"
    assert created["tag_list"] == ["web", "idor"]
    node = vault.get_node(created["id"])
    assert node is not None
    assert node.content == "GET /api/user/1 without auth"


def test_quick_capture_falls_back_to_the_first_content_line(vault: Vault) -> None:
    api = Api(vault)

    created = api.quick_capture({"content": "nmap -sC -sV -p- 10.10.10.42"})

    assert created["title"] == "nmap -sC -sV -p- 10.10.10.42"
    node = vault.get_node(created["id"])
    assert node is not None
    assert node.content == "nmap -sC -sV -p- 10.10.10.42"


def test_quick_capture_rejects_empty_input(vault: Vault) -> None:
    api = Api(vault)

    with pytest.raises(ApiError):
        api.quick_capture({"title": "  ", "content": ""})


def test_quick_capture_through_the_dispatcher(vault: Vault) -> None:
    api = Api(vault)

    created = api.handle("quick_capture", {"content": "SAML request"})

    assert created["title"] == "SAML request"
