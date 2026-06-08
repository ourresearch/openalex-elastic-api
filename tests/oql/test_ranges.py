"""Numeric ranges + multi-word value quoting (oxjob #363).

Three behaviors locked here, all surfaced by a single real user URL
(`publication_year:2019-2023,primary_location.source.type:"journal|ebook
platform|book series|conference",…`):

  1. A num field takes a hyphen range — `year is 2019-2023` (closed; also float
     ranges for FWCI), sugar for the two-bound implicit-AND. Only a CLOSED range
     renders as the dash form; a single-ended bound stays an inequality (`year >=
     2019`), though the open dash spellings `2019-` / `-2023` are accepted on input.
     A strict integer bound PAIR collapses to an inclusive range (`> 42 and < 100`
     -> `43-99`); a lone strict bound and float strict pairs stay as inequalities.
  2. The URL parser strips an enclosing quote pair from a non-search value before
     the pipe-split (engine `is_quoted` parity), so `"a|b c|d"` is OR of [a, "b c",
     d] with multi-word values kept whole.
  3. A multi-word value atom (`ebook platform`) is QUOTED on render so it
     re-parses as one atom instead of an adjacency-AND.

Pure: no app boot. Run with
    PYTHONPATH=. pytest tests/oql/test_ranges.py -q --noconftest
"""
import pytest

import tests.oql._qt_loader  # noqa: F401  (installs the pure query_translation stub)

from query_translation.oql_lang import parse, render, OQLError  # noqa: E402
from query_translation.oqo_canonicalizer import canonicalize_oqo  # noqa: E402
from query_translation.url_parser import parse_url_to_oqo  # noqa: E402


def _c(oql):
    return canonicalize_oqo(parse(oql)).to_dict()


def _leaves(oql):
    return _c(oql)["filter_rows"]


# --------------------------------------------------------------------------- #
# 1. range parsing -> bound leaves
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("oql,expected", [
    ("works where year is 2019-2023",
     [{"column_id": "publication_year", "value": 2023, "operator": "<="},
      {"column_id": "publication_year", "value": 2019, "operator": ">="}]),
    ("works where year is 2019-",
     [{"column_id": "publication_year", "value": 2019, "operator": ">="}]),
    ("works where year is -2023",
     [{"column_id": "publication_year", "value": 2023, "operator": "<="}]),
    ("works where FWCI is 1.5-3.0",
     [{"column_id": "fwci", "value": 3.0, "operator": "<="},
      {"column_id": "fwci", "value": 1.5, "operator": ">="}]),
])
def test_range_parses_to_bound_leaves(oql, expected):
    assert _leaves(oql) == expected


def test_closed_range_matches_url_form():
    """`year is 2019-2023` is the same OQO the URL parser builds from a range."""
    url = canonicalize_oqo(parse_url_to_oqo(
        "works", filter_string="publication_year:2019-2023")).to_dict()
    assert _c("works where year is 2019-2023") == url


def test_leading_hyphen_is_open_upper_not_negative():
    assert _leaves("works where year is -2023") == [
        {"column_id": "publication_year", "value": 2023, "operator": "<="}]


# --------------------------------------------------------------------------- #
# 2. range rendering (canonical dash form)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("src,want", [
    # only a CLOSED range renders as the dash form
    ("works where year >= 2019 and year <= 2023", "works where year is 2019-2023"),
    ("works where FWCI is 1.5-3.0", "works where FWCI is 1.5-3.0"),
    # a SINGLE-ended bound stays an inequality — the open dash form is input-only
    ("works where year >= 2019", "works where year >= 2019"),
    ("works where year <= 2023", "works where year <= 2023"),
    ("works where year is 2019-", "works where year >= 2019"),
    ("works where year is -2023", "works where year <= 2023"),
])
def test_render_dash_form(src, want):
    assert render(canonicalize_oqo(parse(src))) == want


def test_strict_integer_pair_collapses_to_inclusive():
    # Jason's example: > 42 and < 100 -> 43-99
    assert render(canonicalize_oqo(parse(
        "works where year > 42 and year < 100"))) == "works where year is 43-99"
    assert render(canonicalize_oqo(parse(
        "works where citation count > 42 and citation count < 100"
    ))) == "works where citation count is 43-99"


def test_lone_strict_bound_stays_inequality():
    # a single strict bound has no clean inclusive spelling -> keep > / <
    assert render(canonicalize_oqo(parse(
        "works where citation count > 100"))) == "works where citation count > 100"


def test_float_strict_pair_stays_inequalities():
    # FWCI is a float field — no ±1 — so a strict pair is NOT collapsed
    out = render(canonicalize_oqo(parse("works where FWCI > 1.5 and FWCI < 3.0")))
    assert "1.5-" not in out and "is 1.5" not in out
    assert "FWCI > 1.5" in out and "FWCI < 3.0" in out


@pytest.mark.parametrize("oql", [
    "works where year is 2019-2023",
    "works where year is 2019-",
    "works where year is -2023",
    "works where year > 42 and year < 100",
    "works where citation count > 100",
    "works where FWCI is 1.5-3.0",
])
def test_range_round_trips(oql):
    once = _c(oql)
    twice = canonicalize_oqo(parse(render(canonicalize_oqo(parse(oql))))).to_dict()
    assert once == twice


# --------------------------------------------------------------------------- #
# 3. multi-word value quoting + URL quote-stripping
# --------------------------------------------------------------------------- #
def test_multiword_value_must_be_quoted_to_parse():
    # bare multi-word value re-reads as adjacency-AND -> the undelimited error
    with pytest.raises(OQLError) as e:
        parse('works where source type is ebook platform')
    assert e.value.code == "OQL_UNDELIMITED_TERM_LIST"
    # quoted is one atom
    assert _leaves('works where source type is "ebook platform"') == [
        {"column_id": "primary_location.source.type", "value": "ebook platform"}]


def test_render_quotes_multiword_value():
    oql = render(canonicalize_oqo(parse(
        'works where source type is (journal or "ebook platform")')))
    assert '"ebook platform"' in oql and " journal" in oql


def test_url_strips_enclosing_quotes_before_pipe_split():
    """`"a|b c|d"` (engine: quotes = spaces-literal, pipe still ORs) -> 4 clean
    values, multi-word kept whole; no phantom quote stuck to the ends."""
    o = canonicalize_oqo(parse_url_to_oqo(
        "works",
        filter_string='primary_location.source.type:"journal|ebook platform|book series|conference"',
    )).to_dict()
    vals = sorted(f["value"] for f in o["filter_rows"][0]["filters"])
    assert vals == ["book series", "conference", "ebook platform", "journal"]


def test_full_user_case_round_trips():
    """The exact URL Jason reported renders and re-parses to the same OQO."""
    filt = ('publication_year:2019-2023,'
            'primary_location.source.type:"journal|ebook platform|book series|conference",'
            'has_doi:true,authorships.institutions.lineage:i4210155119')
    o = canonicalize_oqo(parse_url_to_oqo("works", filter_string=filt)).to_dict()
    oql = render(canonicalize_oqo(parse_url_to_oqo("works", filter_string=filt)))
    assert "year is 2019-2023" in oql
    assert "source type is" in oql                 # display name, not raw column id
    assert canonicalize_oqo(parse(oql)).to_dict() == o
