from __future__ import annotations

from redscribe.fuzzy import fuzzy_score, rank_items


def test_fuzzy_score_requires_subsequence() -> None:
    assert fuzzy_score("htb", "HTB Corporate") is not None
    assert fuzzy_score("xyz", "HTB Corporate") is None
    assert fuzzy_score("", "anything") == 0


def test_fuzzy_score_rewards_prefix_and_contiguous_matches() -> None:
    prefix = fuzzy_score("corp", "Corporate box")
    scattered = fuzzy_score("corp", "A c o r p")
    assert prefix is not None
    assert scattered is not None
    assert prefix > scattered


def test_rank_items_sorts_and_limits() -> None:
    items = ["Linux privilege escalation", "Nmap quick reference", "HTB Corporate"]
    ranked = rank_items("nmap", items, key=lambda item: item)
    assert ranked[0] == "Nmap quick reference"
    assert rank_items("htb", items, key=lambda item: item, limit=1) == ["HTB Corporate"]
    assert rank_items("", items, key=lambda item: item) == items
    assert rank_items("", items, key=lambda item: item, limit=2) == items[:2]


def test_rank_items_preserves_order_for_ties() -> None:
    items = ["alpha", "alphabet"]
    assert rank_items("alpha", items, key=lambda item: item)[0] == "alpha"
