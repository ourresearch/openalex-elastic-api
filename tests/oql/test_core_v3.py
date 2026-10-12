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


@pytest.mark.parametrize("oxford,plain", [
    ("rank authors by count of works about kelp. Show sum of citations, mean FWCI, and h-index.",
     "rank authors by count of works about kelp. Show sum of citations, mean FWCI and h-index."),
    ("get works co-authored by [A](A5067184382), [B](A5074743574), and [C](A5047110566)",
     "get works co-authored by [A](A5067184382), [B](A5074743574) and [C](A5047110566)"),
])
def test_oxford_comma_canonical_both_read(oxford, plain):
    # the Oxford comma in the echo (Jason 2026-10-12); the list without it reads the same
    assert parse_core(oxford).to_dict() == parse_core(plain).to_dict()
    assert render_core(parse_core(plain), lambda v, c=None: {"A5067184382": "A", "A5074743574": "B",
                                                            "A5047110566": "C"}.get(str(v))) == oxford


@pytest.mark.parametrize("col", ["topics.id", "topics.subfield.id", "topics.field.id", "topics.domain.id"])
def test_any_topic_never_reads_as_the_primary_topic(col):
    # the echo must not cover a key (Jason 2026-10-12): `in the topic [X]` is the primary
    # topic, so any of a work's topics stays in the `where` form and reads back as itself
    from query_translation.oqo import LeafFilter
    oqo = OQO(get_rows="works", filter_rows=[LeafFilter(col, "T10033" if col == "topics.id" else "17")])
    text = render_core(oqo, lambda v, c=None: "X")
    assert " in the " not in text
    assert parse_core(text).filter_rows[0].column_id == col


# --- the baseline over the page's groups, its switch, and the flip by config (2026-10-12) ---

def test_baseline_lists_the_groups_on_the_page():
    from query_translation.execution import _baseline_on_page_groups
    boqo = OQO(get_rows="works", group_by=[GroupBy(column_id="authorships.countries"),
                                          GroupBy(column_id="open_access.is_oa")])
    page = [{"key": "https://openalex.org/countries/CA",
             "groups": [{"key": "true"}, {"key": "false"}]},
            {"key": "https://openalex.org/countries/US", "groups": [{"key": "true"}]}]
    out = _baseline_on_page_groups(boqo, page)
    assert out.group_by[0].values == ["CA", "US"]
    assert out.group_by[1].values == ["true", "false"]


def test_baseline_leaves_a_level_open_when_a_group_cant_be_named_again():
    from query_translation.execution import _baseline_on_page_groups
    boqo = OQO(get_rows="works", group_by=[GroupBy(column_id="sustainable_development_goals.id")])
    out = _baseline_on_page_groups(boqo, [{"key": "https://openalex.org/sdgs/3"}, {"key": "unknown"}])
    assert out.group_by[0].values is None


def test_a_listed_value_is_named_like_the_plain_split():
    # `13` from a listed split reads `https://openalex.org/fields/13`, as a split by field writes it
    from query_translation.analytics import Level, _row_key
    lv = Level(0, GroupBy(column_id="primary_topic.field.id"), "filters",
               column_id="primary_topic.field.id", group_entity="fields")
    assert _row_key("13", lv, "works") == _row_key(13, lv, "works") == "https://openalex.org/fields/13"


@pytest.mark.parametrize("args,style,want", [
    ("", "pipeline", False), ("?oql_style=core", "pipeline", True), ("", "core", True),
    ("?baseline=false", "core", False), ("?baseline=true", "pipeline", True),
])
def test_baseline_switch(monkeypatch, args, style, want):
    from flask import Flask
    from query_translation import oql_lang
    from query_translation.x_query import baseline_wanted
    monkeypatch.setattr(oql_lang, "CANONICAL_STYLE", style)
    with Flask(__name__).test_request_context("/" + args):
        assert baseline_wanted() is want


def test_the_core_flip_is_a_config_change(monkeypatch):
    # OQL_CANONICAL_STYLE=core: the echo is core where core can say it, else today's pipeline text
    from flask import Flask
    from query_translation import oql_lang
    from query_translation.x_query import build_x_query
    monkeypatch.setattr(oql_lang, "CANONICAL_STYLE", "core")
    core = parse_core("break down works about kelp by year")
    piped = OQO(get_rows="works", group_by=[GroupBy(column_id="publication_year")],
                calculate=[Measure("max", "cited_by_count")])     # no core name for max
    with Flask(__name__).test_request_context("/"):
        assert build_x_query(core, sort_operands=False)["oql"] == "break down works about kelp by year"
        assert build_x_query(piped, sort_operands=False)["oql"].startswith("get works;\nthen, group")
