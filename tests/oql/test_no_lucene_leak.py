"""OQL values never leak search-engine (Lucene) syntax into the engine (oxjob #865).

OQL is explicit pseudo-English. An OQL value is compiled to classic params and
handed to the same `SearchOpenAlex` builder as the classic API, so any operator
character the engine still honors inside a value was silently live in OQL:
`title has (cancer~1)` ran as Lucene fuzzy matching (prod: 3,212,830 vs
3,126,171 for `cancer`), and a typed `"machine learning"~3` was mangled into the
phrase AND a stray stemmed token `~3`. `|` (the classic URL's OR-pipe) rendered
`has (dog|cat)` (an AND, 3,232) to the SAME url leg as `has (dog or cat)`
(371,675) — a url-leg lie. `\\` is Lucene's escape character.

Decision (Jason, 2026-08-22, option b): reject, don't escape — the existing OQL
idiom for a micro-syntax misuse (`bar*` → OQL_WILDCARD_NEEDS_EXACT). `~` →
OQL_NO_FUZZY (points at `within N (…)`; fuzzy is a planned explicit keyword,
built only when users ask); `|` / `\\` → OQL_CHAR_NOT_OPERATOR.

And the other direction: a classic-URL query that legitimately uses documented
`term~N` fuzzy has NO honest OQL form, so its `x_query.oql` leg is `null` with an
`oql_unavailable` reason — exactly as the `url` leg already goes null for an OQO
with no URL form — never OQL that means something else.

Pure: no app boot. Run with
    PYTHONPATH=. pytest tests/oql/test_no_lucene_leak.py -q --noconftest
"""
import pytest

import tests.oql._qt_loader  # noqa: F401

from query_translation.diagnostics import OQLError  # noqa: E402
from query_translation.oql_lang import render as render_oql  # noqa: E402
from query_translation.oql_parser import OQLParseError, parse_oql_to_oqo  # noqa: E402
from query_translation.oql_renderer import render_oqo_to_oql  # noqa: E402
from query_translation.url_parser import parse_url_to_oqo  # noqa: E402
from query_translation.x_query import build_x_query  # noqa: E402


def _engine_error(oql):
    """The engine OQLError behind the parser's OQLParseError wrapper (chained as
    __cause__; the wrapper itself carries only message/position)."""
    with pytest.raises(OQLParseError) as ei:
        parse_oql_to_oqo(oql)
    cause = ei.value.__cause__
    assert isinstance(cause, OQLError)
    return cause


def _code(oql):
    return _engine_error(oql).code


# --- typed `~` is rejected everywhere a value can appear ------------------------

@pytest.mark.parametrize("oql", [
    "works where title has (cancer~1)",                       # bare fuzzy
    'works where title has ("cancer~1")',                     # quoted fuzzy
    "works where title has (cancer~)",                        # bare fuzzy, default distance
    'works where title has ("machine learning"~3)',           # typed phrase slop
    'works where title has ("machine"~3~"learning")',         # typed binary proximity
    "works where title has (deep cancer~1 learning)",         # inside a bare run
    'works where title has (deep "cancer~1" learning)',       # quoted escape inside a run
    'works where title has (within 3 ("smart~1", "phone"))',  # proximity operand
    "works where title has (within 3 (smart~1, phone))",
    "works where title/abstract has (cancer~1)",
    "works where full text has (cancer~1)",
])
def test_tilde_is_rejected_with_no_fuzzy(oql):
    assert _code(oql) == "OQL_NO_FUZZY"


def test_no_fuzzy_fixit_points_at_within():
    err = _engine_error('works where title has ("machine learning"~3)')
    assert "within N" in err.fixit
    assert "fuzzy" in err.fixit


@pytest.mark.parametrize("oql", [
    "works where title has (dog|cat)",
    'works where title has ("dog|cat")',
    "works where title has (dog cat|bird)",
    "works where title has (a\\b)",
    'works where title has ("a\\b")',
    'works where title has (within 3 ("dog|cat", "bird"))',
])
def test_pipe_and_backslash_are_rejected(oql):
    assert _code(oql) == "OQL_CHAR_NOT_OPERATOR"


# --- OQL's own micro-syntax is untouched --------------------------------------

@pytest.mark.parametrize("oql,expected_value", [
    ('works where title has (within 3 ("machine", "learning"))', '"machine"~3~"learning"'),
    ('works where title has (within 3 (machine, learning))', '"machine"~3~"learning"'),
    ('works where title has ("bar*")', "bar*"),
    ('works where title has ("wom?n")', "wom?n"),
    ('works where title has ("machine learning")', '"machine learning"'),
    ("works where title has (dog or cat)", None),
])
def test_sanctioned_surfaces_still_parse(oql, expected_value):
    oqo = parse_oql_to_oqo(oql)
    if expected_value is not None:
        assert oqo.filter_rows[0].value == expected_value
    # and they round-trip
    assert parse_oql_to_oqo(render_oqo_to_oql(oqo)).to_dict() == oqo.to_dict()


def test_within_generated_tilde_renders_and_reparses():
    """The canonical `"a"~N~"b"` encoding is OQL's own — generated, never typed."""
    oqo = parse_oql_to_oqo('works where title has (within 3 ("machine", "learning"))')
    assert render_oqo_to_oql(oqo) == 'works where title has (within 3 ("machine", "learning"))'


# --- the classic door: fuzzy stays, but its OQL leg is honest ------------------

def test_classic_fuzzy_has_no_oql_render():
    oqo = parse_url_to_oqo("works", scoped_searches={"search.title": "cancer~1"})
    assert oqo.filter_rows[0].value == "cancer~1"        # classic fuzzy is kept
    with pytest.raises(OQLError) as ei:
        render_oql(oqo, resolver=None)
    assert ei.value.code == "OQL_NO_FUZZY"


def test_x_query_oql_leg_is_null_with_reason_for_classic_fuzzy():
    oqo = parse_url_to_oqo("works", scoped_searches={"search.title.exact": "cancer~1 treatment"})
    xq = build_x_query(oqo)
    assert xq["oql"] is None
    assert "fuzzy" in xq["oql_unavailable"]
    assert xq["url"] is not None                          # the url leg stays faithful
    assert xq["oqo"]["filter_rows"]


def test_x_query_has_no_reason_key_when_oql_renders():
    xq = build_x_query(parse_url_to_oqo("works", scoped_searches={"search.title": "cancer"}))
    assert xq["oql"] == "works where title has (cancer)"
    assert "oql_unavailable" not in xq


def test_single_phrase_slop_still_renders_as_within():
    """`"p"~N` (documented classic slop) keeps its deliberately lossy `within N`
    render (#514) — only bare fuzzy has no surface at all."""
    oqo = parse_url_to_oqo("works", scoped_searches={"search.title.exact": '"machine learning"~3'})
    assert render_oql(oqo, resolver=None) == 'works where title has (within 3 ("machine", "learning"))'
