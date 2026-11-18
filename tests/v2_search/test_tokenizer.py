from __future__ import annotations

from redscribe.v2.search.synonyms import SynonymSet, merge_synonyms
from redscribe.v2.search.tokenizer import (
    collapse_whitespace,
    fold_text,
    index_terms,
    is_stopword,
    ngrams,
    normalize_token,
    split_compound,
    stem,
    token_key,
    token_positions,
    tokenize,
    tokenize_query,
    word_count,
)


def test_folding_and_normalization() -> None:
    assert fold_text("Café  Scan!!") == "cafe scan!!"
    assert normalize_token("Café-Scan!") == "cafescan"
    assert collapse_whitespace("  a\n\tb  ") == "a b"


def test_stopwords_and_stems() -> None:
    assert is_stopword("the")
    assert not is_stopword("nmap")
    assert stem("scanning").startswith("scan")
    assert stem("stories") in {"stori", "story"}
    assert token_key("STORY") == token_key("story")


def test_compound_splitting() -> None:
    parts = split_compound("subDomainScan")
    assert "sub" in parts or "domain" in parts
    assert split_compound("simple") == ()


def test_tokenize_keeps_offsets_and_fields() -> None:
    tokens = tokenize("Nmap found 80 ports", field="content")
    assert [token.normalized for token in tokens] == ["nmap", "found", "80", "ports"]
    assert tokens[0].start == 0
    assert tokens[0].end == 4
    assert tokens[1].field == "content"
    assert tokenize("", field="title") == ()


def test_tokenize_query_preserves_phrases() -> None:
    tokens = tokenize_query('"sql injection" +port* -noise~ title:flag^2')
    assert any(token.kind == "phrase" for token in tokens)
    assert any(token.normalized == "sql injection" for token in tokens)
    assert any(token.normalized == "port" for token in tokens)


def test_index_terms_include_prefixes_and_ngrams() -> None:
    tokens = tokenize("scanning ports")
    terms = set(index_terms(tokens[0]))
    assert "scan" in terms
    assert any(term.startswith("sca") for term in terms)
    assert ngrams(("alpha", "beta", "gamma"))[:2] == ("alpha beta", "beta gamma")


def test_word_count_and_positions() -> None:
    assert word_count("one two three") == 3
    assert token_positions("nmap nmap scan", "nmap") == (0, 1)


def test_synonym_expansion_is_transitive() -> None:
    groups = SynonymSet([("scan", "nmap"), ("nmap", "scanner")])
    assert "nmap" in groups.expand("scan")
    assert "scan" in groups.expand("nmap")
    assert groups.related("scan", "scanner")
    assert groups.canonical("NMAP") in {"nmap", "scan"}


def test_synonym_sets_merge_and_serialize() -> None:
    left = SynonymSet([("scan", "nmap")])
    right = SynonymSet([("port", "openport")])
    merged = merge_synonyms(left, right)
    assert merged.size >= left.size
    payload = merged.as_dict()
    assert "groups" in payload or "size" in payload
    assert SynonymSet.empty().size == 0
    assert SynonymSet.from_mapping({"scan": ["nmap"]}).related("scan", "nmap")


def test_expand_terms_preserves_originals() -> None:
    groups = SynonymSet([("scan", "nmap")])
    expanded = groups.expand_terms(("scan",))
    assert "nmap" in expanded
    assert expanded == groups.expand("scan", include_self=False)
