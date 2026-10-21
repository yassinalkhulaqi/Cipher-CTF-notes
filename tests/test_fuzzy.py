from __future__ import annotations

from redscribe.domain.fuzzy import fuzzy_match, fuzzy_score, rank_items


def test_fuzzy_score_requires_subsequence() -> None:
    assert fuzzy_score("htb", "HTB Corporate") is not None
    assert fuzzy_score("xyz", "HTB Corporate") is None
    assert fuzzy_score("", "anything") == 0
    assert fuzzy_match("htb", "HTB Corporate") is True
    assert fuzzy_match("xyz", "HTB Corporate") is False
    assert fuzzy_match("", "anything") is True
    assert fuzzy_score("corporate-box", "box") is None


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


def test_word_boundaries_beat_scattered_letters() -> None:
    boundary = fuzzy_score("ws", "Windows Server")
    scattered = fuzzy_score("ws", "Awards Show")
    assert boundary is not None
    assert scattered is not None
    assert boundary > scattered


def test_fuzzy_ranking_is_case_insensitive_and_unbounded() -> None:
    items = ["PrivEsc Notes", "HTB Corporate", "Évidence"]
    assert rank_items("privesc", items, key=lambda item: item) == ["PrivEsc Notes"]
    assert rank_items("évi", items, key=lambda item: item) == ["Évidence"]
    assert rank_items("missing", items, key=lambda item: item) == []
