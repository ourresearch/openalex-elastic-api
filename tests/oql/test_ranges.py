"""Numeric bounds + multi-word value quoting (oxjob #363).

Behaviors locked here:

  1. The dash range literal was REMOVED as OQL surface syntax (charter decision
     24): a num range is written as explicit endpoint clauses
     `year >= 2019 and year <= 2023`. Typing a dash range (`year is 2019-2023`,
     open-ended `2019-` / `-2023`) is a hard `OQL_RANGE_LITERAL_REMOVED` error;
     a non-numeric dash term still falls through to `OQL_BAD_NUMBER`.
  2. A bound pair renders as two endpoint clauses, lower bound first
     (`year >= 2019 and year <= 2023`); strict bounds stay strict — `> 42 and
     < 100` is NOT rewritten to the inclusive `43-99` (the ±1 collapse was
     dropped with the literal). The OpenAlex URL range form still parses and
     still renders endpoints, so URL round-trip survives.
  3. The URL parser strips an enclosing quote pair from a non-search value before
     the pipe-split (engine `is_quoted` parity), so `"a|b c|d"` is OR of [a, "b c",
     d] with multi-word values kept whole; a multi-word value atom is QUOTED on
     render so it re-parses as one atom (unrelated to ranges — kept green).

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
# 1. the dash range literal is REJECTED (decision 24)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("oql", [
    "works where year is 2019-2023",   # closed
    "works where year is 2019-",       # open lower
    "works where year is -2023",       # open upper
    "works where FWCI is 1.5-3.0",     # float closed
    "works where citation count is 1-100",
])
def test_dash_range_literal_is_rejected(oql):
    with pytest.raises(OQLError) as e:
        parse(oql)
    assert e.value.code == "OQL_RANGE_LITERAL_REMOVED"


def test_range_reject_fixit_echoes_the_endpoints():
    with pytest.raises(OQLError) as e:
        parse("works where FWCI is 1.5-3.0")
    assert "FWCI >= 1.5 and FWCI <= 3.0" in e.value.fixit


def test_non_numeric_dash_term_is_still_bad_number_not_a_range():
    with pytest.raises(OQLError) as e:
        parse("works where year is 2019-abc")
    assert e.value.code == "OQL_BAD_NUMBER"


# --------------------------------------------------------------------------- #
# 2. endpoint parsing -> bound leaves (lower-first canonical order)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("oql,expected", [
    ("works where year >= 2019 and year <= 2023",
     [{"column_id": "publication_year", "value": 2019, "operator": ">="},
      {"column_id": "publication_year", "value": 2023, "operator": "<="}]),
    ("works where year >= 2019",
     [{"column_id": "publication_year", "value": 2019, "operator": ">="}]),
    ("works where year <= 2023",
     [{"column_id": "publication_year", "value": 2023, "operator": "<="}]),
    ("works where FWCI >= 1.5 and FWCI <= 3.0",
     [{"column_id": "fwci", "value": 1.5, "operator": ">="},
      {"column_id": "fwci", "value": 3.0, "operator": "<="}]),
])
def test_endpoints_parse_to_bound_leaves(oql, expected):
    assert _leaves(oql) == expected


def test_closed_range_matches_url_form():
    """The endpoint form is the same OQO the URL parser builds from a range —
    URL round-trip survives even though the OQL dash literal is gone."""
    url = canonicalize_oqo(parse_url_to_oqo(
        "works", filter_string="publication_year:2019-2023")).to_dict()
    assert _c("works where year >= 2019 and year <= 2023") == url


def test_url_range_renders_endpoint_clauses_not_dash():
    out = render(canonicalize_oqo(parse_url_to_oqo(
        "works", filter_string="publication_year:2019-2023")))
    assert out == "works where all (year >= 2019, year <= 2023)"
    assert "-" not in out.split("where", 1)[1]  # no dash range anywhere


# --------------------------------------------------------------------------- #
# 3. endpoint rendering (lower-first; strict stays strict — no collapse)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("src,want", [
    ("works where year >= 2019 and year <= 2023", "works where all (year >= 2019, year <= 2023)"),
    ("works where year <= 2023 and year >= 2019", "works where all (year >= 2019, year <= 2023)"),
    ("works where FWCI >= 1.5 and FWCI <= 3.0", "works where all (FWCI >= 1.5, FWCI <= 3.0)"),
    ("works where year >= 2019", "works where year >= 2019"),
    ("works where year <= 2023", "works where year <= 2023"),
])
def test_render_endpoint_form(src, want):
    assert render(canonicalize_oqo(parse(src))) == want


def test_strict_integer_pair_stays_strict_no_collapse():
    # decision 24: > 42 and < 100 is NOT rewritten to the inclusive 43-99
    assert render(canonicalize_oqo(parse(
        "works where year > 42 and year < 100"))) == "works where all (year > 42, year < 100)"
    assert render(canonicalize_oqo(parse(
        "works where citation count > 42 and citation count < 100"
    ))) == "works where all (citation count > 42, citation count < 100)"


def test_lone_strict_bound_stays_inequality():
    assert render(canonicalize_oqo(parse(
        "works where citation count > 100"))) == "works where citation count > 100"


def test_float_strict_pair_stays_inequalities():
    out = render(canonicalize_oqo(parse("works where FWCI > 1.5 and FWCI < 3.0")))
    assert "1.5-" not in out and "is 1.5" not in out
    assert "FWCI > 1.5" in out and "FWCI < 3.0" in out


@pytest.mark.parametrize("oql", [
    "works where year >= 2019 and year <= 2023",
    "works where year >= 2019",
    "works where year <= 2023",
    "works where year > 42 and year < 100",
    "works where citation count > 100",
    "works where FWCI >= 1.5 and FWCI <= 3.0",
])
def test_bound_round_trips(oql):
    once = _c(oql)
    twice = canonicalize_oqo(parse(render(canonicalize_oqo(parse(oql))))).to_dict()
    assert once == twice


# --------------------------------------------------------------------------- #
# 4. multi-word value quoting + URL quote-stripping (unrelated to ranges)
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
    """The exact URL Jason reported renders and re-parses to the same OQO —
    the range now renders as endpoint clauses (decision 24)."""
    filt = ('publication_year:2019-2023,'
            'primary_location.source.type:"journal|ebook platform|book series|conference",'
            'has_doi:true,authorships.institutions.lineage:i4210155119')
    o = canonicalize_oqo(parse_url_to_oqo("works", filter_string=filt)).to_dict()
    oql = render(canonicalize_oqo(parse_url_to_oqo("works", filter_string=filt)))
    # endpoint clauses, not a dash range (the render is width-wrapped to lines)
    assert "year >= 2019" in oql and "year <= 2023" in oql
    assert "2019-2023" not in oql
    assert "source type is" in oql                 # display name, not raw column id
    assert canonicalize_oqo(parse(oql)).to_dict() == o
