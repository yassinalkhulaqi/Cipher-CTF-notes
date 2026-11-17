from __future__ import annotations

import pytest

from redscribe.domain.fuzzy import (
    edit_distance,
    fold_key,
    fuzzy_match,
    fuzzy_score,
    is_typo_of,
    rank_items,
    rank_scored,
    rank_tokens,
    token_aware_score,
    word_tokens,
)


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


def test_fold_key_strips_accents_case_and_spacing() -> None:
    assert fold_key("  ÉVidence  More ") == "evidence more"
    assert fold_key("Évidence") == fold_key("Evidence")
    assert fold_key("Naïve  café") == "naive cafe"


def test_word_tokens_split_folded_text() -> None:
    assert word_tokens("Linux-priv_esc Notes") == ("linux", "priv_esc", "notes")
    assert word_tokens("Évidence") == ("evidence",)
    assert word_tokens("   ") == ()


def test_edit_distance_counts_inserts_deletes_substitutions_and_transpositions() -> None:
    assert edit_distance("cat", "cat") == 0
    assert edit_distance("cat", "cats") == 1
    assert edit_distance("cat", "cut") == 1
    assert edit_distance("abcd", "abdc") == 1
    assert edit_distance("abc", "xyz", max_distance=3) == 3
    assert edit_distance("abc", "abcdef", max_distance=2) is None
    assert edit_distance("abc", "xyz", max_distance=0) is None


def test_edit_distance_rejects_negative_bound() -> None:
    with pytest.raises(ValueError, match="non-negative"):
        edit_distance("a", "b", max_distance=-1)


def test_is_typo_of_requires_distinct_words_of_useful_length() -> None:
    assert is_typo_of("corp", "crop") is True
    assert is_typo_of("corp", "corp") is False
    assert is_typo_of("abc", "abd") is False
    assert is_typo_of("evidence", "evidnece") is True


def test_token_aware_score_prefers_exact_over_prefix_and_subsequence() -> None:
    exact = token_aware_score("corporate", "Corporate")
    prefix = token_aware_score("corp", "Corporate")
    substring = token_aware_score("orpo", "Corporate")
    scattered = token_aware_score("corp", "C o r p")
    assert exact is not None
    assert prefix is not None
    assert substring is not None
    assert scattered is not None
    assert exact > prefix > substring > scattered


def test_token_aware_score_folds_accents_and_case() -> None:
    folded = token_aware_score("évi", "Évidence")
    plain = token_aware_score("evi", "Evidence")
    assert folded is not None
    assert plain is not None
    assert folded == plain
    assert token_aware_score("évi", "Unrelated") is None


def test_token_aware_score_requires_every_query_token() -> None:
    assert token_aware_score("htb corporate", "HTB") is None
    assert token_aware_score("linux escalation", "Linux Privilege Escalation") is not None
    assert token_aware_score("missing", "HTB Corporate") is None


def test_token_aware_score_tolerates_single_edit_typos() -> None:
    exact = token_aware_score("recon", "Recon Notes")
    typo = token_aware_score("recan", "Recon Notes")
    assert exact is not None
    assert typo is not None
    assert exact > typo


def test_token_aware_score_handles_empty_inputs() -> None:
    assert token_aware_score("  ", "Anything") == 0
    assert token_aware_score("query", "") is None
    assert token_aware_score("", "") == 0


def test_legacy_fuzzy_score_does_not_fold_accents() -> None:
    assert fuzzy_score("évi", "Evidence") is None
    assert token_aware_score("évi", "Evidence") is not None


def test_rank_scored_exposes_scores_and_original_positions() -> None:
    items = ["HTB Corporate", "Nmap Notes", "HTB Corp"]
    ranked = rank_scored("htb corp", items, key=lambda item: item)
    assert [entry.item for entry in ranked][:2] == ["HTB Corp", "HTB Corporate"]
    assert ranked[0].order == 2
    assert ranked[0].score > 0
    assert {entry.order for entry in ranked} <= set(range(len(items)))


def test_rank_scored_tie_break_is_deterministic() -> None:
    items = ["bbb", "aa", "cc", "aa"]
    ranked = rank_scored("ignored", items, key=lambda item: item, scorer=lambda _q, _t: 10)
    assert [entry.item for entry in ranked] == ["aa", "aa", "cc", "bbb"]
    assert [entry.order for entry in ranked[:2]] == [1, 3]
    assert [entry.item for entry in rank_scored("", items, key=lambda item: item, limit=3)] == [
        "bbb",
        "aa",
        "cc",
    ]


def test_rank_tokens_delegates_to_rank_scored() -> None:
    items = ["Nmap quick reference", "HTB Corporate"]
    assert rank_tokens("nmap", items, key=lambda item: item) == ["Nmap quick reference"]
    assert rank_tokens("nmap", items, key=lambda item: item, limit=0) == []
