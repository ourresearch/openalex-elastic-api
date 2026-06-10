"""Within-field NOT (`!`) in a `.search` value — OXURL→OQO parsing (oxjob #431).

The compact OpenAlex form `term!"phrase"` means *term AND NOT (exact) phrase*
(live-verified on prod: `title_and_abstract.search:teacher!"academic teacher"`
== `teacher` minus the exact phrase). The parser used to keep the whole string
as one opaque `contains` value, dropping the `!` so the NOT silently became an
AND. These tests pin the decomposition: leading run is positive, each `!run` is
a negated clause on the same field; quoted run → exact (`.search.exact`), bare
run → stemmed (`.search`). Source: zd#8101 (Claire Stansfield, UCL EPPI-Centre).
"""
import tests.oql._qt_loader  # noqa: F401  (installs the pure query_translation stub)

from query_translation.oqo_canonicalizer import canonicalize_oqo  # noqa: E402
from query_translation.url_parser import (  # noqa: E402
    parse_single_filter,
    parse_url_to_oqo,
)

SEARCH = "title_and_abstract.search"
EXACT = "title_and_abstract.search.exact"


def _leaves(value, field=SEARCH):
    """Canonicalized filter_rows for a single `field:value` pair."""
    parsed = parse_single_filter(field, value)
    rows = parsed if isinstance(parsed, list) else [parsed]
    from query_translation.oqo import OQO

    return canonicalize_oqo(OQO(get_rows="works", filter_rows=rows)).to_dict()[
        "filter_rows"
    ]


def test_quoted_operand_routes_to_exact_negated():
    """`teacher!"academic teacher"` → contains teacher AND NOT exact phrase."""
    rows = _leaves('teacher!"academic teacher"')
    assert {
        "column_id": SEARCH,
        "value": "teacher",
        "operator": "contains",
    } in rows
    assert {
        "column_id": EXACT,
        "value": '"academic teacher"',
        "operator": "contains",
        "is_negated": True,
    } in rows
    # No `!` survives inside any value string.
    assert all("!" not in str(r.get("value", "")) for r in rows)


def test_matches_oql_oracle_round_trip():
    """The parsed OQO equals the one the OQL `does not contain` oracle produces."""
    from tests.oql.oql_v2 import parse as oql_parse

    got = _leaves('teacher!"academic teacher"')
    want = canonicalize_oqo(
        oql_parse(
            "works where title and abstract contains teacher "
            'and title and abstract does not contain "academic teacher"'
        )
    ).to_dict()["filter_rows"]
    assert got == want


def test_bare_operand_stays_stemmed():
    """A bare (unquoted) negated operand stays on the stemmed `.search` column."""
    rows = _leaves("England!Wales")
    assert {"column_id": SEARCH, "value": "England", "operator": "contains"} in rows
    assert {
        "column_id": SEARCH,
        "value": "Wales",
        "operator": "contains",
        "is_negated": True,
    } in rows


def test_multiple_nots_chain():
    """`a!b!c` = a AND NOT b AND NOT c (every run after the first is negated)."""
    rows = _leaves("a!b!c")
    negated = {r["value"] for r in rows if r.get("is_negated")}
    positive = {r["value"] for r in rows if not r.get("is_negated")}
    assert negated == {"b", "c"}
    assert positive == {"a"}


def test_pipe_or_composes_with_not_outermost():
    """`a|b!"c d"` = OR(a, AND(b, NOT exact "c d")) — `|` is the outermost op."""
    rows = _leaves('a|b!"c d"')
    assert len(rows) == 1
    branch = rows[0]
    assert branch["join"] == "or"
    members = branch["filters"]
    # one plain leaf `a`, one AND-branch `b AND NOT "c d"`
    leaf_a = [m for m in members if m.get("value") == "a"]
    and_branch = [m for m in members if m.get("join") == "and"]
    assert leaf_a and and_branch
    sub = and_branch[0]["filters"]
    assert {"column_id": SEARCH, "value": "b", "operator": "contains"} in sub
    assert {
        "column_id": EXACT,
        "value": '"c d"',
        "operator": "contains",
        "is_negated": True,
    } in sub


def test_leading_bang_is_value_level_negation_unchanged():
    """A LEADING `!` is the existing value-level negation, not within-field NOT."""
    rows = _leaves('!"academic teacher"')
    assert len(rows) == 1
    assert rows[0]["is_negated"] is True
    # stays on the stemmed column (existing behavior), value keeps its quotes
    assert rows[0]["column_id"] == SEARCH


def test_trailing_bang_with_no_operand_stays_opaque():
    """`hello!` (no operand after `!`) is left as an opaque value, unchanged."""
    rows = _leaves("hello!")
    assert rows == [
        {"column_id": SEARCH, "value": "hello!", "operator": "contains"}
    ]


def test_bang_inside_quotes_is_literal():
    """A `!` inside a quoted phrase is literal text, never a separator."""
    rows = _leaves('"hello!world"')
    assert len(rows) == 1
    assert rows[0]["value"] == '"hello!world"'
    assert not rows[0].get("is_negated")


def test_plus_is_not_an_operator():
    """Regression guard: `+` is a literal (URL-decoded space), not an operator."""
    rows = _leaves("nicotine+snus")
    assert rows == [
        {"column_id": SEARCH, "value": "nicotine+snus", "operator": "contains"}
    ]


def test_non_search_field_ignores_bang_decomposition():
    """Within-field NOT only applies to `.search` columns; other fields keep the
    leading-`!` semantics and never split on a mid-string `!`."""
    rows = _leaves("article!review", field="type")
    # `type` is not a `.search` field → no decomposition; one opaque leaf.
    assert len(rows) == 1
    assert rows[0]["value"] == "article!review"


def test_full_url_path():
    """End-to-end through `parse_url_to_oqo` (the public entry point)."""
    oqo = parse_url_to_oqo(
        "works", filter_string='title_and_abstract.search:teacher!"academic teacher"'
    )
    rows = canonicalize_oqo(oqo).to_dict()["filter_rows"]
    assert {
        "column_id": EXACT,
        "value": '"academic teacher"',
        "operator": "contains",
        "is_negated": True,
    } in rows
