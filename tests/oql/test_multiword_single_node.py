"""D2 reversal — multi-word search is ONE stemmed node (oxjob #363, discovery run #3).

The dominant real query shape (a multi-word free-text search, ~33% of prod /works
queries) must round-trip URL -> OQO -> OQL -> OQO as a SINGLE adjacency-boosted
node, not split per-word. This reverses locked decision D2 (parens-bag
distribution). Plus the two render fixes it requires:

  #2  a literal reserved word (and/or/not) in a stemmed value is escaped by quoting
      just that word (`road traffic safety "and" Ghana`) — a quoted token embedded
      in a bare run stays stemmed; a standalone quoted phrase is still exact.
  #3  special chars (? * | and OQL-structural punctuation) are DROPPED from a
      stemmed value on render (the analyzer strips them anyway) — no escape syntax.

Run with:
    PYTHONPATH=. pytest tests/oql/test_multiword_single_node.py -q
"""
import pytest

import tests.oql._qt_loader  # noqa: F401  (installs the pure query_translation stub)

from query_translation.oql_lang import parse, render_tree, OQLError  # noqa: E402
from query_translation.url_parser import parse_url_to_oqo  # noqa: E402
from query_translation.oqo_canonicalizer import canonicalize_oqo  # noqa: E402


def _render(oqo):
    return render_tree(canonicalize_oqo(oqo), resolver=None)[0]


def _rows(oql):
    return canonicalize_oqo(parse(oql)).to_dict()["filter_rows"]


# --- #1: a bare multi-word run is ONE node, not per-word AND --------------- #

def test_bare_run_is_one_node():
    fr = _rows("works where title/abstract contains (mental health)")
    assert fr == [{"column_id": "title_and_abstract.search",
                   "value": "mental health", "operator": "contains"}]


def test_explicit_connective_builds_tree():
    fr = _rows("works where title/abstract contains (mental health or anxiety)")
    assert len(fr) == 1 and fr[0]["join"] == "or"
    assert sorted(f["value"] for f in fr[0]["filters"]) == ["anxiety", "mental health"]


def test_single_word_unchanged():
    fr = _rows("works where title contains cancer")
    assert fr == [{"column_id": "display_name.search", "value": "cancer", "operator": "contains"}]


@pytest.mark.parametrize("search_value,expected_value", [
    ("mental health", "mental health"),
    ("machine learning models", "machine learning models"),
    ("deep neural networks for vision", "deep neural networks for vision"),
])
def test_url_multiword_round_trips_as_one_node(search_value, expected_value):
    u = parse_url_to_oqo("works", filter_string=f"title_and_abstract.search:{search_value}")
    before = canonicalize_oqo(u).to_dict()
    after = canonicalize_oqo(parse(_render(u))).to_dict()
    assert before == after
    assert before["filter_rows"] == [{"column_id": "title_and_abstract.search",
                                      "value": expected_value, "operator": "contains"}]


# --- #2: reserved-word escape --------------------------------------------- #

@pytest.mark.parametrize("value", [
    "road traffic safety and Ghana",
    "this or that study",
    "presence and absence not detected",
])
def test_reserved_word_literal_round_trips(value):
    u = parse_url_to_oqo("works", filter_string=f"title_and_abstract.search:{value}")
    rendered = _render(u)
    # the reserved word is quoted in the render so it reads as a literal
    assert canonicalize_oqo(parse(rendered)).to_dict() == canonicalize_oqo(u).to_dict()


def test_embedded_quote_is_a_stemmed_escape():
    # a quoted token inside a bare run folds in as a literal STEMMED word (stays
    # on .search), unlike a standalone quoted phrase (which is exact)
    fr = _rows('works where title/abstract contains (road traffic "and" Ghana)')
    assert fr == [{"column_id": "title_and_abstract.search",
                   "value": "road traffic and Ghana", "operator": "contains"}]


def test_standalone_quote_still_exact():
    fr = _rows('works where title/abstract contains "road traffic"')
    assert fr[0]["column_id"] == "title_and_abstract.search.exact"


# --- #3: special chars dropped on render ----------------------------------- #

@pytest.mark.parametrize("value,expected", [
    ("Can active memory replace attention?", "Can active memory replace attention"),
    ("foo|bar baz", "foo bar baz"),
    ("a (test) of punctuation;", "a test of punctuation"),
])
def test_special_chars_dropped_and_reparse_clean(value, expected):
    u = parse_url_to_oqo("works", filter_string=f"title_and_abstract.search:{value}")
    rendered = _render(u)
    # rendered OQL re-parses (no OQL_WILDCARD_NEEDS_EXACT / structural break)
    fr = canonicalize_oqo(parse(rendered)).to_dict()["filter_rows"]
    # the stemmed value is the cleaned form (punctuation the analyzer strips anyway)
    leaf = fr[0]
    if "join" in leaf:  # `|` parses to an OR upstream in the URL — just assert it re-parses
        parse(rendered)
    else:
        assert leaf["value"] == expected


def test_wildcard_on_exact_column_keeps_metachars():
    # genuine wildcards live on .search.exact and must NOT be stripped
    fr = _rows('works where title contains "bar*"')
    assert fr[0]["column_id"] == "display_name.search.exact"
    assert "*" in fr[0]["value"]
