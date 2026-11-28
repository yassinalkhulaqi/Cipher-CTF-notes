"""Tests for the parser, evaluator, facets, clustering, and persistence."""

from __future__ import annotations

import json

import pytest

from redscribe.v4.events import EventBus, EventKind, InMemoryOutbox
from redscribe.v4.query.service import (
    ClusteringEngine,
    FacetEngine,
    QueryLexer,
    QueryParser,
    SavedQueryService,
    SearchEvaluator,
    default_engines,
)
from redscribe.v4.query.storage import QueryStore, QueryStoreView, merge_stores
from redscribe.v4.query.types import (
    BooleanOp,
    DuplicateQueryNameError,
    FieldName,
    Operator,
    QueryCapacityError,
    QueryError,
    QueryNotFoundError,
    QuerySyntaxError,
    SavedQuery,
)

ID_A = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
ID_B = "11111111-2222-3333-4444-555555555555"
ID_C = "99999999-8888-7777-6666-555555555555"
TIME_A = "2026-01-01T00:00:00.000Z"
TIME_B = "2026-01-02T00:00:00.000Z"


def make_documents() -> list[dict[str, object]]:
    return [
        {
            "id": "n1",
            "title": "SQL injection playbook",
            "body": "Union based injection notes",
            "tags": ["web", "ctf"],
            "kind": "note",
            "status": "open",
            "flag": True,
            "target": "192.0.2.10",
            "author": "ada",
            "count": 9,
        },
        {
            "id": "n2",
            "title": "Buffer overflow",
            "body": "Stack canaries and return addresses",
            "tags": ["pwn"],
            "kind": "finding",
            "status": "closed",
            "flag": False,
            "target": "example.test",
            "author": "grace",
            "count": 2,
        },
        {
            "id": "n3",
            "title": "Web cache deception",
            "body": "Investigating CDN caches",
            "tags": ["web"],
            "kind": "note",
            "status": "open",
            "flag": True,
            "author": "ada",
        },
    ]


@pytest.fixture
def parser() -> QueryParser:
    return QueryParser()


@pytest.fixture
def evaluator() -> SearchEvaluator:
    return SearchEvaluator()


def ids(documents: list[dict[str, object]]) -> list[str]:
    return [str(document["id"]) for document in documents]


def test_lexer_token_kinds_and_positions() -> None:
    tokens = QueryLexer().tokenize('title:contains("a,b") AND tag:in(web,ctf)')
    kinds = [token.kind.value for token in tokens]
    assert kinds[:5] == ["word", "colon", "word", "lparen", "quoted"]
    assert "comma" in kinds
    assert "rparen" in kinds
    assert tokens[-1].kind.value == "eof"
    assert tokens[0].position == 0


def test_lexer_decodes_escapes() -> None:
    tokens = QueryLexer().tokenize(r'title:"a\"b\\c\nd"')
    assert tokens[2].value == 'a"b\\c\nd'


def test_lexer_rejects_bad_escape_and_unterminated_quote() -> None:
    with pytest.raises(QuerySyntaxError, match="invalid escape sequence"):
        QueryLexer().tokenize(r'title:"bad\q"')
    with pytest.raises(QuerySyntaxError, match="unterminated quoted value"):
        QueryLexer().tokenize('title:"bad')
    with pytest.raises(QuerySyntaxError, match="unterminated escape sequence"):
        QueryLexer().tokenize('title:"bad\\')


def test_parser_simple_clauses(parser: QueryParser) -> None:
    query = parser.parse("title:contains(sql)")
    assert query.token_count == 1
    token = query.tokens[0]
    assert token.field is FieldName.TITLE
    assert token.operator is Operator.CONTAINS
    assert token.value == "sql"
    assert token.boolean is None
    assert not token.free_text


def test_parser_boolean_expression(parser: QueryParser) -> None:
    query = parser.parse("title:contains(sql) AND tag:in(web,ctf)")
    assert query.token_count == 2
    assert query.tokens[0].boolean is None
    assert query.tokens[1].boolean is BooleanOp.AND
    assert query.tokens[1].values == ("web", "ctf")
    assert query.normalized == "title:contains(sql) AND tag:in(web,ctf)"


def test_parser_or_and_negation(parser: QueryParser) -> None:
    query = parser.parse('title:"sql injection" OR NOT status:=closed')
    assert query.tokens[0].boolean is None
    assert query.tokens[1].boolean is BooleanOp.OR
    assert query.tokens[1].negated
    assert query.tokens[1].value == "closed"
    assert query.tokens[1].operator is Operator.EQ


def test_parser_symbol_operators(parser: QueryParser) -> None:
    query = parser.parse("status:!=closed AND title:>Buffer OR title:<Webb")
    assert [token.operator for token in query.tokens] == [
        Operator.NEQ,
        Operator.GT,
        Operator.LT,
    ]
    assert [token.value for token in query.tokens] == ["closed", "Buffer", "Webb"]
    assert [token.boolean for token in query.tokens] == [None, BooleanOp.AND, BooleanOp.OR]


def test_parser_default_operator_and_alias(parser: QueryParser) -> None:
    assert parser.parse("title:sql").tokens[0].operator is Operator.EQ
    assert parser.parse("title:startswith(sql)").tokens[0].operator is Operator.STARTS_WITH
    assert parser.parse("tag:has(web)").tokens[0].operator is Operator.CONTAINS


def test_parser_quoted_values_and_escaping(parser: QueryParser) -> None:
    query = parser.parse(r'body:contains("say \"hello\"")')
    assert query.tokens[0].value == 'say "hello"'
    single = parser.parse("title:'single quoted'")
    assert single.tokens[0].value == "single quoted"


def test_parser_implicit_free_text(parser: QueryParser) -> None:
    query = parser.parse("sql injection")
    assert query.token_count == 2
    assert all(token.free_text for token in query.tokens)
    assert query.tokens[1].boolean is BooleanOp.AND
    assert query.free_text_terms == ("sql", "injection")


def test_parser_empty_expression(parser: QueryParser) -> None:
    query = parser.parse("   ")
    assert query.is_empty
    assert query.normalized == ""


def test_parser_honours_expression_length(parser: QueryParser) -> None:
    with pytest.raises(QueryError, match="expression exceeds 500"):
        parser.parse("x" * 501)


@pytest.mark.parametrize(
    ("expression", "message"),
    [
        ("bogus:foo", "unknown field: bogus"),
        ("title:regex(foo)", "unknown operator: regex"),
        ("title:", "expected a value"),
        ("title:contains()", "accepts exactly one"),
        ("tag:in()", "value list must not be empty"),
        ("tag:in(web,)", "trailing comma"),
        ("tag:in(,web)", "missing value in list"),
        ("tag:in(web,ctf", "unterminated value list"),
        ('title:"unterminated', "unterminated quoted value"),
        ("AND title:foo", "unexpected boolean operator"),
        ("title:foo AND", "expected a clause"),
        ("title:foo,bar", "unexpected token: ,"),
        ("(title:foo)", "parenthesised boolean groups"),
        ("title:contains(a b)", "unexpected token in value list: b"),
    ],
)
def test_parser_rejects_invalid_expressions(
    parser: QueryParser, expression: str, message: str
) -> None:
    with pytest.raises(QuerySyntaxError, match=message):
        parser.parse(expression)


def test_parser_error_has_position(parser: QueryParser) -> None:
    with pytest.raises(QuerySyntaxError) as info:
        parser.parse("title:foo AND bogus:x")
    assert info.value.position == 14
    assert "at position 14" in str(info.value)


def test_evaluator_equality_and_contains(evaluator: SearchEvaluator, parser: QueryParser) -> None:
    documents = make_documents()
    assert ids(
        evaluator.filter_documents(documents, parser.parse('title:="SQL injection playbook"'))
    )
    assert ids(evaluator.filter_documents(documents, parser.parse("title:contains(SQL)"))) == ["n1"]
    assert ids(evaluator.filter_documents(documents, parser.parse("title:starts_with(Web)"))) == [
        "n3"
    ]


def test_evaluator_not_equal(evaluator: SearchEvaluator, parser: QueryParser) -> None:
    documents = make_documents()
    result = evaluator.filter_documents(documents, parser.parse("status:!=closed"))
    assert ids(result) == ["n1", "n3"]


def test_evaluator_in_operator(evaluator: SearchEvaluator, parser: QueryParser) -> None:
    documents = make_documents()
    result = evaluator.filter_documents(documents, parser.parse("tag:in(pwn,web)"))
    assert ids(result) == ["n1", "n2", "n3"]
    single = evaluator.filter_documents(documents, parser.parse("tag:in(web)"))
    assert ids(single) == ["n1", "n3"]


def test_evaluator_relational_operators(evaluator: SearchEvaluator, parser: QueryParser) -> None:
    documents = make_documents()
    numeric = {"id": "n4", "target": "10"}
    assert evaluator.matches(numeric, parser.parse("target:>5"))
    assert evaluator.matches(numeric, parser.parse("target:<11"))
    assert not evaluator.matches(numeric, parser.parse("target:>10"))
    lexical = evaluator.filter_documents(documents, parser.parse('title:>"Buffer overflow"'))
    assert ids(lexical) == ["n1", "n3"]


def test_evaluator_boolean_precedence(evaluator: SearchEvaluator, parser: QueryParser) -> None:
    documents = make_documents()
    query = parser.parse("status:=open AND kind:=note OR author:=grace")
    assert ids(evaluator.filter_documents(documents, query)) == ["n1", "n2", "n3"]
    with pytest.raises(QuerySyntaxError, match="parenthesised boolean groups"):
        parser.parse("status:=open AND (id:=n1)")


def test_evaluator_negation(evaluator: SearchEvaluator, parser: QueryParser) -> None:
    documents = make_documents()
    assert ids(evaluator.filter_documents(documents, parser.parse("NOT status:=closed"))) == [
        "n1",
        "n3",
    ]
    assert ids(evaluator.filter_documents(documents, parser.parse("NOT tag:in(pwn)"))) == [
        "n1",
        "n3",
    ]


def test_evaluator_missing_fields_and_aliases(evaluator: SearchEvaluator) -> None:
    document: dict[str, object] = {"id": "x", "tags": ["web"], "text": "hello", "state": "open"}
    assert evaluator.field_values(document, FieldName.TAG) == ("web",)
    assert evaluator.field_values(document, FieldName.BODY) == ("hello",)
    assert evaluator.field_values(document, FieldName.STATUS) == ("open",)
    assert evaluator.field_values(document, FieldName.TITLE) == ()


def test_evaluator_neq_on_missing_field(evaluator: SearchEvaluator, parser: QueryParser) -> None:
    document: dict[str, object] = {"id": "x", "title": "known"}
    assert evaluator.matches(document, parser.parse("author:!=nobody"))
    assert not evaluator.matches(document, parser.parse("author:=nobody"))


def test_evaluator_free_text_searches_all_fields(
    evaluator: SearchEvaluator, parser: QueryParser
) -> None:
    document: dict[str, object] = {"id": "x", "target": "192.0.2.1", "tags": ["ctf"]}
    assert evaluator.matches(document, parser.parse("192.0.2"))
    assert evaluator.matches(document, parser.parse("ctf"))
    assert not evaluator.matches(document, parser.parse("missing"))


def test_evaluator_empty_query_matches_all(evaluator: SearchEvaluator, parser: QueryParser) -> None:
    documents = make_documents()
    assert len(evaluator.filter_documents(documents, parser.parse(""))) == 3


def test_evaluator_ranking_and_trace(evaluator: SearchEvaluator, parser: QueryParser) -> None:
    documents = make_documents()
    query = parser.parse("title:contains(web) OR body:contains(cache)")
    ranked = evaluator.rank_documents(documents, query)
    assert ids(ranked)[0] == "n3"
    assert len(evaluator.rank_documents(documents, query, limit=1)) == 1
    trace = evaluator.trace(documents[2], query)
    assert trace.matched
    assert trace.matched_clauses >= 1
    assert trace.score > 0
    assert "clauses" in trace.to_dict()


def test_evaluator_warnings(evaluator: SearchEvaluator, parser: QueryParser) -> None:
    assert "empty query matches every document" in evaluator.validate(parser.parse(""))
    warnings = evaluator.validate(parser.parse("tag:in(web)"))
    assert any("single-value in clause" in warning for warning in warnings)


def test_facet_counts_and_definitions(evaluator: SearchEvaluator) -> None:
    engine = FacetEngine(max_values=5)
    results = make_documents()
    tags = engine.facet(results, FieldName.TAG)
    assert [item.value for item in tags.values] == ["web", "ctf", "pwn"]
    assert {item.value: item.count for item in tags.values} == {
        "web": 2,
        "pwn": 1,
        "ctf": 1,
    }
    assert engine.counts(results, FieldName.AUTHOR)["ada"] == 2
    assert engine.counts([{"id": "x"}], FieldName.TAG) == {"(unknown)": 1}


def test_facet_selection_and_filtering(evaluator: SearchEvaluator) -> None:
    engine = FacetEngine()
    results = make_documents()
    facets = engine.build(results, (FieldName.KIND, FieldName.STATUS), {"status": ["open"]})
    assert facets[1].selected_values == ("open",)
    filtered = engine.filter_by_facets(
        results, {FieldName.STATUS: ["open"], FieldName.KIND: ["note"]}
    )
    assert ids(filtered) == ["n1", "n3"]
    assert engine.filter_by_facets(results, {FieldName.STATUS: []}) == results


def test_facet_limits(evaluator: SearchEvaluator) -> None:
    with pytest.raises(QueryError, match="max_values must be >= 1"):
        FacetEngine(0)
    limited = FacetEngine().facet(make_documents(), FieldName.TAG, limit=1)
    assert len(limited.values) == 1


def test_clustering_groups_and_summary() -> None:
    engine = ClusteringEngine(max_samples=1)
    clusters = engine.group(make_documents(), FieldName.KIND)
    assert [cluster.key for cluster in clusters] == ["note", "finding"]
    assert clusters[0].count == 2
    assert clusters[0].sample_count == 1
    summary = engine.summary(clusters)
    assert summary["results"] == 3
    assert summary["clusters"] == 2
    assert summary["largest"] == "note"


def test_clustering_multiple_fields_and_missing_values() -> None:
    engine = ClusteringEngine()
    groups = engine.group_many(make_documents(), (FieldName.STATUS, FieldName.TARGET))
    assert set(groups) == {"status", "target"}
    assert groups["status"][0].key == "open"
    with pytest.raises(QueryError, match="invalid clustering limits"):
        ClusteringEngine(max_clusters=0)


def test_saved_query_service_crud_and_events() -> None:
    clock_values = iter([TIME_A, TIME_B, TIME_B, TIME_B])
    ids_values = iter([ID_A, ID_B, ID_C])
    bus = EventBus(InMemoryOutbox())
    service = SavedQueryService(
        bus=bus,
        clock=lambda: next(clock_values),
        id_factory=lambda: next(ids_values),
    )
    created = service.save("sql hunt", "title:contains(sql)")
    assert created.id == ID_A
    assert created.created_at == TIME_A
    assert service.get(ID_A) == created
    assert service.list() == (created,)
    renamed = service.rename(ID_A, "sql investigations")
    assert renamed.name == "sql investigations"
    updated = service.replace_expression(ID_A, "body:contains(sql)")
    assert updated.expression == "body:contains(sql)"
    duplicate = service.duplicate(ID_A, "sql copy")
    assert duplicate.expression == "body:contains(sql)"
    assert duplicate.id == ID_B
    removed = service.delete(ID_A)
    assert removed.id == ID_A
    assert service.list() == (duplicate,)

    events = bus.published
    assert len(events) == 5
    assert all(event.kind is EventKind.QUERY_SAVED for event in events)
    assert events[0].payload["action"] == "saved"
    assert events[1].payload["action"] == "renamed"
    assert [record.kind for record in bus.outbox.records(EventKind.QUERY_SAVED)] == [
        "query.saved"
    ] * 5


def test_saved_query_service_errors() -> None:
    ids_values = iter([ID_A, ID_B, ID_C])
    service = SavedQueryService(clock=lambda: TIME_A, id_factory=lambda: next(ids_values))
    with pytest.raises(QueryError, match="at least one clause"):
        service.save("empty", "")
    with pytest.raises(QuerySyntaxError, match="unknown field"):
        service.save("bad", "nope:x")
    created = service.save("sql", "title:contains(sql)")
    with pytest.raises(DuplicateQueryNameError, match="already exists"):
        service.save("SQL", "title:contains(x)")
    with pytest.raises(QueryNotFoundError, match="unknown saved query"):
        service.get(ID_B)
    with pytest.raises(QueryNotFoundError):
        service.delete(ID_B)
    assert created.id == ID_A


def test_saved_query_service_export() -> None:
    service = SavedQueryService(clock=lambda: TIME_A, id_factory=lambda: ID_A)
    service.save("sql", "title:contains(sql)")
    payload = json.loads(service.export_json())
    assert payload["queries"][0]["name"] == "sql"


def test_default_engines_are_independent() -> None:
    first = default_engines()
    second = default_engines()
    assert len(first) == 4
    assert first[0] is not second[0]
    assert isinstance(first[3], ClusteringEngine)


def test_store_crud_and_name_index() -> None:
    store = QueryStore()
    first = SavedQuery(id=ID_A, name="sql", expression="title:contains(sql)", created_at=TIME_A)
    second = SavedQuery(id=ID_B, name="web", expression="tag:in(web)", created_at=TIME_B)
    assert store.put(first) is first
    assert store.put(second) is second
    assert store.count() == 2
    assert store.has("SQL")
    assert ID_A in store
    assert store.get(ID_A) == first
    assert store.require(ID_B) == second
    assert [query.name for query in store.list()] == ["sql", "web"]
    assert [query.name for query in store.insertion_order()] == ["sql", "web"]
    assert [query.name for query in store.recent(1)] == ["web"]
    assert store.names() == ("sql", "web")
    assert store.ids() == (ID_A, ID_B)

    renamed = store.rename(ID_A, "sqli")
    assert renamed.name == "sqli"
    assert not store.has("sql")
    assert store.delete(ID_A)
    assert not store.delete(ID_A)
    assert store.count() == 1
    with pytest.raises(QueryNotFoundError):
        store.require(ID_A)
    with pytest.raises(DuplicateQueryNameError):
        store.put(SavedQuery(id=ID_C, name="WEB", expression="title:x", created_at=TIME_B))
    store.clear()
    assert len(store) == 0


def test_store_capacity_and_validation() -> None:
    with pytest.raises(QueryError, match="capacity must be >= 1"):
        QueryStore(0)
    store = QueryStore(capacity=1)
    store.put(SavedQuery(id=ID_A, name="one", expression="title:x", created_at=TIME_A))
    with pytest.raises(QueryCapacityError, match="capacity reached"):
        store.put(SavedQuery(id=ID_B, name="two", expression="title:x", created_at=TIME_B))


def test_store_json_export_import_and_snapshot() -> None:
    store = QueryStore()
    store.put(SavedQuery(id=ID_A, name="sql", expression="title:x", created_at=TIME_A))
    exported = store.export_json()
    assert '"name": "sql"' in exported
    other = QueryStore()
    assert other.import_json(exported) == 1
    assert other.get(ID_A) is not None
    assert other.import_json(exported) == 1
    assert other.count() == 1

    restored = QueryStore()
    assert restored.restore(store.snapshot()) == 1
    assert restored.list() == store.list()
    with pytest.raises(QueryError, match="unsupported snapshot version"):
        restored.restore({"version": 99})
    with pytest.raises(QueryError, match="malformed query store JSON"):
        store.import_json("{not json")
    with pytest.raises(QueryError, match="must be an object"):
        store.import_json("[]")
    with pytest.raises(QueryError, match="duplicate name in imported data"):
        store.import_json(
            json.dumps(
                {
                    "queries": [
                        {"id": ID_A, "name": "dup", "expression": "title:x", "created_at": TIME_A},
                        {"id": ID_B, "name": "DUP", "expression": "title:y", "created_at": TIME_B},
                    ]
                }
            ),
            replace=True,
        )


def test_store_rejects_bad_import_items() -> None:
    store = QueryStore()
    with pytest.raises(QueryError, match="must be a JSON object"):
        store.import_json(json.dumps({"queries": ["bad"]}))
    with pytest.raises(QueryError, match="duplicate id in imported data"):
        store.import_json(
            json.dumps(
                {
                    "queries": [
                        {"id": ID_A, "name": "a", "expression": "title:x", "created_at": TIME_A},
                        {"id": ID_A, "name": "b", "expression": "title:y", "created_at": TIME_B},
                    ]
                }
            )
        )


def test_store_view_and_merge() -> None:
    left = QueryStore()
    right = QueryStore()
    left.put(SavedQuery(id=ID_A, name="sql", expression="title:x", created_at=TIME_A))
    right.put(SavedQuery(id=ID_B, name="web", expression="tag:x", created_at=TIME_B))
    right.put(SavedQuery(id=ID_C, name="SQL", expression="title:y", created_at=TIME_B))
    view = QueryStoreView(left)
    assert view.all()[0]["name"] == "sql"
    assert view.by_name("SQL") is not None
    assert view.by_name("missing") is None
    assert view.page(0, 1)[0]["id"] == ID_A
    with pytest.raises(QueryError, match="invalid page bounds"):
        view.page(-1, 2)
    merged = merge_stores([left, right])
    assert merged.count() == 2
    assert set(merged.names()) == {"sql", "web"}


def test_service_defaults_are_wired() -> None:
    service = SavedQueryService()
    assert isinstance(service.store, QueryStore)
    assert isinstance(service.parser, QueryParser)
