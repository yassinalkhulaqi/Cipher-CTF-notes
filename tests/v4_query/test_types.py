"""Unit tests for query-language value types and validation."""

from __future__ import annotations

import pytest

from redscribe.v4.contracts import Capability, ErrorCode
from redscribe.v4.query.types import (
    MAX_EXPRESSION_LENGTH,
    MAX_NAME_LENGTH,
    QUERY_CAPABILITIES,
    BooleanOp,
    DuplicateQueryNameError,
    FacetDefinition,
    FacetValue,
    FieldName,
    Operator,
    ParsedQuery,
    QueryCapacityError,
    QueryError,
    QueryNotFoundError,
    QuerySyntaxError,
    QueryToken,
    ResultCluster,
    SavedQuery,
    as_int,
    coerce_text,
    coerce_values,
    normalize_expression,
    sequence_of,
)

FIXED_ID = "11111111-2222-3333-4444-555555555555"
FIXED_TIME = "2026-01-02T03:04:05.000Z"


def test_field_name_parse_and_labels() -> None:
    assert FieldName.parse(" TITLE ") is FieldName.TITLE
    assert FieldName.parse("body") is FieldName.BODY
    assert FieldName.parse("unknown") is None
    assert FieldName.require("tag") is FieldName.TAG
    assert len(list(FieldName)) == 8
    for field in FieldName:
        assert field.label
        assert field.suggested_operators


def test_field_name_require_raises_positioned_error() -> None:
    with pytest.raises(QuerySyntaxError, match="unknown field: bogus at position 7"):
        FieldName.require("bogus", 7)


def test_field_name_operator_recommendations() -> None:
    assert Operator.IN in FieldName.TAG.suggested_operators
    assert Operator.CONTAINS in FieldName.TITLE.suggested_operators
    assert Operator.EQ in FieldName.STATUS.suggested_operators
    assert Operator.IN not in FieldName.BODY.suggested_operators


def test_operator_parse_aliases() -> None:
    assert Operator.parse("=") is Operator.EQ
    assert Operator.parse("==") is Operator.EQ
    assert Operator.parse("!") is Operator.NEQ
    assert Operator.parse("<>") is Operator.NEQ
    assert Operator.parse("startswith") is Operator.STARTS_WITH
    assert Operator.parse("SW") is Operator.STARTS_WITH
    assert Operator.parse("has") is Operator.CONTAINS
    assert Operator.parse("oneof") is Operator.IN
    assert Operator.parse(">=") is Operator.GT
    assert Operator.parse("nope") is None


def test_operator_properties() -> None:
    assert Operator.IN.is_set
    assert not Operator.EQ.is_set
    assert Operator.GT.is_relational
    assert Operator.LT.is_relational
    assert not Operator.CONTAINS.is_relational
    for operator in Operator:
        assert operator.label
        assert Operator.require(operator.value) is operator


def test_operator_require_raises() -> None:
    with pytest.raises(QuerySyntaxError, match="unknown operator: regex"):
        Operator.require("regex", 3)


def test_boolean_operators_and_precedence() -> None:
    assert BooleanOp.parse("AND") is BooleanOp.AND
    assert BooleanOp.parse("or") is BooleanOp.OR
    assert BooleanOp.parse("NOT") is BooleanOp.NOT
    assert BooleanOp.parse("xor") is None
    assert BooleanOp.OR.precedence < BooleanOp.AND.precedence < BooleanOp.NOT.precedence


def test_normalize_expression_collapses_whitespace_and_keywords() -> None:
    assert normalize_expression('  title:contains("sql")   and   TAG:in(web,ctf) ') == (
        'title:contains("sql") AND tag:in(web,ctf)'
    )
    assert normalize_expression('body:"AND OR not"') == 'body:"AND OR not"'


def test_scalar_coercion_helpers() -> None:
    assert coerce_text(None) == ""
    assert coerce_text(True) == "true"
    assert coerce_text(False) == "false"
    assert coerce_text(42) == "42"
    assert coerce_values(["a", None, 2]) == ("a", "2")
    assert coerce_values({"a": 1}) == ("1",)
    assert sequence_of([1, 2]) == (1, 2)
    assert sequence_of("abc") == ()
    assert as_int("12") == 12
    assert as_int("-3") == -3
    assert as_int("bad", 9) == 9
    assert as_int(True, 4) == 4


def test_query_token_single_value() -> None:
    token = QueryToken(FieldName.TITLE, Operator.CONTAINS, "sql", position=5)
    assert token.terms == ("sql",)
    assert token.expression == 'title:contains("sql")'
    assert not token.free_text
    assert token.with_boolean(BooleanOp.AND).boolean is BooleanOp.AND


def test_query_token_set_value() -> None:
    token = QueryToken(FieldName.TAG, Operator.IN, values=("web", "ctf"))
    assert token.terms == ("web", "ctf")
    assert token.expression == "tag:in(web, ctf)"


def test_query_token_negated_and_connector_rendering() -> None:
    token = QueryToken(
        FieldName.STATUS,
        Operator.EQ,
        "closed",
        boolean=BooleanOp.OR,
        negated=True,
    )
    assert token.expression == 'OR NOT status:"closed"'


def test_query_token_free_text() -> None:
    token = QueryToken(FieldName.BODY, free_text=True, value="needle")
    assert token.expression == '"needle"'
    assert token.terms == ("needle",)


def test_query_token_validation() -> None:
    with pytest.raises(QueryError, match="requires a non-empty value"):
        QueryToken(FieldName.TITLE, Operator.EQ, "")
    with pytest.raises(QueryError, match="in operator requires at least one value"):
        QueryToken(FieldName.TAG, Operator.IN)
    with pytest.raises(QueryError, match="in values must not be empty"):
        QueryToken(FieldName.TAG, Operator.IN, values=("web", ""))
    with pytest.raises(QueryError, match="too many clause values"):
        QueryToken(FieldName.TAG, Operator.IN, values=tuple(str(i) for i in range(51)))
    with pytest.raises(QueryError, match="free-text token requires"):
        QueryToken(FieldName.BODY, free_text=True, value="  ")


def test_query_token_round_trip() -> None:
    token = QueryToken(
        FieldName.TARGET,
        Operator.NEQ,
        "prod",
        boolean=BooleanOp.AND,
        position=11,
    )
    assert QueryToken.from_dict(token.to_dict()) == token


def test_parsed_query_empty_and_normalized() -> None:
    query = ParsedQuery(raw="  title:foo   and   tag:web  ")
    assert query.is_empty
    assert query.token_count == 0
    assert query.normalized == "title:foo AND tag:web"
    assert query.describe() == "match all"
    assert ParsedQuery().is_empty


def test_parsed_query_properties() -> None:
    tokens = (
        QueryToken(FieldName.TITLE, free_text=True, value="sql"),
        QueryToken(
            FieldName.TAG,
            Operator.IN,
            values=("web",),
            boolean=BooleanOp.AND,
        ),
    )
    query = ParsedQuery(tokens=tokens, raw="sql AND tag:in(web)")
    assert query.fields == frozenset({FieldName.TITLE, FieldName.TAG})
    assert query.connectors == (BooleanOp.AND,)
    assert query.free_text_terms == ("sql",)
    assert query.describe().startswith('"sql"')


def test_parsed_query_length_validation() -> None:
    with pytest.raises(QueryError, match="expression exceeds 500"):
        ParsedQuery(raw="x" * (MAX_EXPRESSION_LENGTH + 1))


def test_parsed_query_round_trip() -> None:
    token = QueryToken(FieldName.AUTHOR, Operator.EQ, "ada", position=2)
    query = ParsedQuery(tokens=(token,), raw='author:"ada"')
    restored = ParsedQuery.from_dict(query.to_dict())
    assert restored == query
    assert ParsedQuery.from_dict({"raw": "title:foo"}).tokens == ()


def test_facet_value_validation_and_selection() -> None:
    value = FacetValue("web", 3)
    assert value.with_selected(True).selected
    assert value.to_dict() == {"value": "web", "count": 3, "selected": False}
    assert FacetValue.from_dict(value.to_dict()) == value
    with pytest.raises(QueryError, match="facet value must not be empty"):
        FacetValue("", 1)
    with pytest.raises(QueryError, match="facet count must be >= 0"):
        FacetValue("web", -1)


def test_facet_definition_defaults_and_counts() -> None:
    facet = FacetDefinition(
        FieldName.TAG, values=(FacetValue("web", 2), FacetValue("ctf", 1, True))
    )
    assert facet.label == "Tag"
    assert facet.total_count == 3
    assert facet.selected_values == ("ctf",)
    assert facet.top(1).values == (FacetValue("web", 2),)
    with pytest.raises(QueryError, match="facet limit must be >= 1"):
        facet.top(0)


def test_facet_definition_selection_and_round_trip() -> None:
    facet = FacetDefinition(
        FieldName.STATUS, values=(FacetValue("open", 4), FacetValue("closed", 2))
    )
    selected = facet.with_selection(["OPEN"])
    assert selected.selected_values == ("open",)
    assert FacetDefinition.from_dict(facet.to_dict()) == facet


def test_facet_definition_rejects_duplicates() -> None:
    with pytest.raises(QueryError, match="duplicate facet value"):
        FacetDefinition(
            FieldName.TAG,
            values=(FacetValue("web", 1), FacetValue("WEB", 2)),
        )


def test_saved_query_validation() -> None:
    query = SavedQuery(
        id=FIXED_ID, name="  sql hunt  ", expression="title:contains(sql)", created_at=FIXED_TIME
    )
    assert query.name == "sql hunt"
    assert query.id == FIXED_ID
    with pytest.raises(QueryError, match="invalid saved query id"):
        SavedQuery(id="nope", name="x", expression="title:x", created_at=FIXED_TIME)
    with pytest.raises(QueryError, match="name must not be empty"):
        SavedQuery(id=FIXED_ID, name="  ", expression="title:x", created_at=FIXED_TIME)
    with pytest.raises(QueryError, match="name exceeds 80"):
        SavedQuery(
            id=FIXED_ID,
            name="x" * (MAX_NAME_LENGTH + 1),
            expression="title:x",
            created_at=FIXED_TIME,
        )
    with pytest.raises(QueryError, match="expression must not be empty"):
        SavedQuery(id=FIXED_ID, name="x", expression="", created_at=FIXED_TIME)
    with pytest.raises(QueryError, match="created_at must not be empty"):
        SavedQuery(id=FIXED_ID, name="x", expression="title:x", created_at="")


def test_saved_query_mutations_and_round_trip() -> None:
    query = SavedQuery(
        id=FIXED_ID, name="sql", expression="title:contains(sql)", created_at=FIXED_TIME
    )
    assert query.rename("sqli").name == "sqli"
    assert query.with_expression("body:contains(x)").expression == "body:contains(x)"
    assert query.name == "sql"
    assert SavedQuery.from_dict(query.to_dict()) == query


def test_result_cluster_validation_and_ratio() -> None:
    cluster = ResultCluster("web", 4, ("a", "b"))
    assert cluster.sample_count == 2
    assert cluster.ratio(8) == 0.5
    assert cluster.ratio(0) == 0.0
    with pytest.raises(QueryError, match="cluster key must not be empty"):
        ResultCluster("", 1)
    with pytest.raises(QueryError, match="cluster count must be >= 0"):
        ResultCluster("web", -1)
    with pytest.raises(QueryError, match="sample_ids cannot exceed"):
        ResultCluster("web", 1, ("a", "b"))
    with pytest.raises(QueryError, match="too many cluster samples"):
        ResultCluster("web", 10, tuple(str(i) for i in range(6)))


def test_result_cluster_merge_and_round_trip() -> None:
    first = ResultCluster("web", 2, ("a",))
    second = ResultCluster("web", 3, ("a", "b"))
    merged = first.merge(second)
    assert merged.count == 5
    assert merged.sample_ids == ("a", "b")
    with pytest.raises(QueryError, match="different keys"):
        first.merge(ResultCluster("ctf", 1))
    assert ResultCluster.from_dict(first.to_dict()) == first


def test_domain_errors_convert_to_api_errors() -> None:
    syntax = QuerySyntaxError("bad token", 4)
    assert "at position 4" in str(syntax)
    assert "position=4" in syntax.to_api_error().details
    assert syntax.to_api_error().code is ErrorCode.INVALID_INPUT
    assert QueryNotFoundError(FIXED_ID).to_api_error().code is ErrorCode.NOT_FOUND
    assert DuplicateQueryNameError("sql").to_api_error().code is ErrorCode.CONFLICT
    assert QueryCapacityError(3).to_api_error().code is ErrorCode.UNAVAILABLE
    assert QueryError("plain").to_api_error().message == "plain"


def test_capability_map_covers_all_actions() -> None:
    assert QUERY_CAPABILITIES["search"] is Capability.READ
    assert QUERY_CAPABILITIES["list"] is Capability.READ
    assert QUERY_CAPABILITIES["get"] is Capability.READ
    assert QUERY_CAPABILITIES["save"] is Capability.WRITE
    assert QUERY_CAPABILITIES["rename"] is Capability.WRITE
    assert QUERY_CAPABILITIES["delete"] is Capability.DELETE
    assert QUERY_CAPABILITIES["export"] is Capability.EXPORT
