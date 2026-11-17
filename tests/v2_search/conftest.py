from __future__ import annotations

from redscribe.storage.db import Vault
from redscribe.v2.search.models import DEFAULT_FIELD_BOOSTS, IndexedDocument, IndexedField
from redscribe.v2.search.tokenizer import tokenize


def make_document(
    doc_id: int,
    *,
    title: str = "Note",
    content: str = "body text",
    tags: tuple[str, ...] = (),
    target: str = "",
    flag: str = "",
    path: str = "",
    status: str = "todo",
    updated_at: str = "2026-01-01T00:00:00Z",
    group: str = "vault",
) -> IndexedDocument:
    values = {
        "title": title,
        "content": content,
        "tags": ", ".join(tags),
        "target": target,
        "flag": flag,
        "path": path,
    }
    fields = tuple(
        IndexedField(
            name=name,
            text=text,
            tokens=tokenize(text, field=name),
            boost=DEFAULT_FIELD_BOOSTS[name],
        )
        for name, text in values.items()
    )
    return IndexedDocument(
        doc_id=doc_id,
        fields=fields,
        metadata={
            "id": doc_id,
            "node_id": doc_id,
            "title": title,
            "tags": tags,
            "tag": tags,
            "status": status,
            "target": target,
            "flag": flag,
            "path": path,
            "pinned": False,
            "created_at": updated_at,
            "updated_at": updated_at,
            "group": group,
            "content_length": len(content),
        },
    )


def seed_vault(vault: Vault) -> tuple[int, int, int]:
    first = vault.create_node(
        "Nmap notes",
        content="nmap scanned ports and found flag CTF{scan}",
        tags="web,recon",
        target="example.com",
        status="active",
        difficulty="easy",
        flag="CTF{scan}",
    )
    second = vault.create_node(
        "Web exploitation",
        content="sql injection bypasses authentication on the target",
        tags="web",
        target="site.tld",
        status="done",
        difficulty="medium",
    )
    third = vault.create_node(
        "Crypto challenge",
        content="RSA modulus factorization notes and keys",
        tags="crypto",
        status="blocked",
        difficulty="hard",
    )
    return first.id, second.id, third.id
