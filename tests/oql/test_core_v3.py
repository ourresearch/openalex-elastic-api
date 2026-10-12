"""OQL core v3 (oxjob #1555): the 44 review cases render and parse back exactly.

Each case in core_v3_cases.json carries the canonical v3 text Jason approved over three
review drafts (2026-10-11) and the OQO it means. Run:
    PYTHONPATH=. pytest tests/oql/test_core_v3.py -q --noconftest
"""
import json
import os

import pytest

import tests.oql._qt_loader  # noqa: F401

from query_translation.oqo import OQO  # noqa: E402
from query_translation.oql_core import render_core  # noqa: E402

DATA = json.load(open(os.path.join(os.path.dirname(__file__), "core_v3_cases.json")))
NAMES = DATA["names"]
CASES = DATA["cases"]


def resolver(value, column=None):
    return NAMES.get(str(value))


def _id(c):
    return f"{c['case'] or c['label']}-{c['shape']}"


@pytest.mark.parametrize("c", CASES, ids=[_id(c) for c in CASES])
def test_renders(c):
    assert render_core(OQO.from_dict(c["oqo"]), resolver) == c["new"]


from query_translation.oql_core import parse_core  # noqa: E402
from query_translation.oqo_canonicalizer import canonicalize_oqo  # noqa: E402

COLLECTION_TYPES = {"col_cat": "institutions", "col_peers": "institutions", "col_jmir": "works"}


def _canon(oqo):
    d = canonicalize_oqo(oqo).to_dict()
    d.pop("sort_by", None)
    return d


@pytest.mark.parametrize("c", CASES, ids=[_id(c) for c in CASES])
def test_parses_back(c):
    got = parse_core(c["new"], COLLECTION_TYPES.get)
    want = OQO.from_dict(c["oqo"])
    assert _canon(got) == _canon(want)
    assert [s.to_dict() for s in got.sort_by] == [s.to_dict() for s in want.sort_by]


@pytest.mark.parametrize("c", CASES, ids=[_id(c) for c in CASES])
def test_round_trips(c):
    assert render_core(parse_core(c["new"], COLLECTION_TYPES.get), resolver) == c["new"]


# --- the automatic baseline ---------------------------------------------------

from query_translation.oql_core import baseline_oqo  # noqa: E402


def _case(n):
    return next(c for c in CASES if c["case"] == n)


@pytest.mark.parametrize("n", [100, 25, 629, 1073, 621, 1061])
def test_baseline_for_one_named_thing(n):
    oqo = OQO.from_dict(_case(n)["oqo"])
    b = baseline_oqo(oqo)
    assert b is not None
    boqo, star = b
    assert star in oqo.filter_rows and star not in boqo.filter_rows
    assert len(boqo.filter_rows) == len(oqo.filter_rows) - 1
    assert [m.measure for m in boqo.calculate] == ["count", "percent_of_those"]
    assert boqo.group_by == oqo.group_by


@pytest.mark.parametrize("n", [105, 934, 66, 29, 19, 625, 665, 169])
def test_no_baseline(n):
    # nothing named, a rank, a plain list, a number, or no single named thing
    assert baseline_oqo(OQO.from_dict(_case(n)["oqo"])) is None


# --- the shared parse entry -----------------------------------------------------

from query_translation.oql_parser import parse_oql_to_oqo  # noqa: E402


@pytest.mark.parametrize("c", CASES, ids=[_id(c) for c in CASES])
def test_entry_point_reads_core(c):
    got = parse_oql_to_oqo(c["new"])
    if any(x in c["new"] for x in ("col_cat", "col_peers")):
        return   # a collection's type needs users-api
    assert _canon(got) == _canon(OQO.from_dict(c["oqo"]))


@pytest.mark.parametrize("old", [
    "get works where institution is [MIT](I63966007) and published since 2020",
    "get works where title-abstract-keywords has kelp; then, group those works by year; finally, summarize using count",
    "get authors at [University of British Columbia](I141945490) since 2022 who published works where title-abstract-keywords has kelp; then, summarize each author using count",
])
def test_entry_point_keeps_todays_meaning(old):
    from query_translation.oql_lang import parse
    assert canonicalize_oqo(parse_oql_to_oqo(old)).to_dict() == canonicalize_oqo(parse(old)).to_dict()


# --- behaviors pinned by the /simplify review (2026-10-11) ----------------------

from query_translation.oql_lang import parse as _old_parse  # noqa: E402
from query_translation.oqo import Measure, GroupBy  # noqa: E402

_R = {"I141945490": "UBC", "Q48": "Asia", "BR": "Brazil"}.get


def _rt(text):
    return render_core(parse_core(text), lambda v, c=None: _R(str(v)))


@pytest.mark.parametrize("text", [
    "get works since 2020 from [Asia](Q48)",
    "rank authors at [UBC](I141945490) by count of works about kelp",
    "rank authors in [Brazil](BR) since 2022 by count of works about kelp",
    "get authors at [UBC](I141945490) in 2+ years since 2022 with an h-index above 50",
])
def test_review_round_trips(text):
    assert _rt(text) == text


def test_bare_at_means_what_todays_parser_means():
    # `at [UBC]` is any year in both grammars (Jason 2026-10-12: OQL hides no assumptions)
    core = parse_core("rank authors at [UBC](I141945490) by count of works about kelp")
    old = _old_parse("get authors at [UBC](I141945490) who published works where "
                     "title-abstract-keywords has kelp; then, summarize each author using count")
    assert core.group_by[0].where == old.group_by[0].where
    assert core.group_by[0].where == parse_core(
        "rank authors ever at [UBC](I141945490) by count of works about kelp").group_by[0].where
    assert "since" not in _rt("rank authors at [UBC](I141945490) by count of works about kelp")


def test_unnamed_measure_keeps_todays_echo():
    oqo = OQO(get_rows="works", group_by=[GroupBy(column_id="publication_year")],
              calculate=[Measure("max", "cited_by_count")])
    assert render_core(oqo) is None


def test_core_sentence_error_is_cores():
    from query_translation.oql_parser import OQLParseError
    with pytest.raises(OQLParseError) as e:
        parse_oql_to_oqo("rank authors by count of works about")
    assert "ends too soon" in str(e.value)
