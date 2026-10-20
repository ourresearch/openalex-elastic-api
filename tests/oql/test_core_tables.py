"""Tables of groups in one sentence (oxjob #1555, D1-D3, 2026-10-20).

`get the <numbers> of <works> by <splits>[, <order>]`: the sentence names the shape, never
the order, so a column sort changes only the order words at the end. `rank` and `break down`
stay accepted input and now echo this form. Run:
    PYTHONPATH=. pytest tests/oql/test_core_tables.py -q --noconftest
"""
import json
import os

import pytest

import tests.oql._qt_loader  # noqa: F401

from query_translation.oqo import OQO, SortBy  # noqa: E402
from query_translation.oql_core import parse_core, render_core  # noqa: E402
from query_translation.oqo_canonicalizer import canonicalize_oqo  # noqa: E402

DATA = json.load(open(os.path.join(os.path.dirname(__file__), "core_v3_cases.json")))
NAMES = DATA["names"]
COLLECTION_TYPES = {"col_cat": "institutions", "col_peers": "institutions", "col_jmir": "works"}


def resolver(value, column=None):
    return NAMES.get(str(value))


def parse(text):
    return canonicalize_oqo(parse_core(text, COLLECTION_TYPES.get), sort_operands=False)


def _without_default_order(oqo: OQO) -> dict:
    d = canonicalize_oqo(oqo).to_dict()      # condition order aside
    sort = d.get("sort_by") or []
    if d.get("group_by") and sort:
        first = d["group_by"][0]["column_id"]
        default = ("key", "asc") if first == "publication_year" else ("count", "desc")
        if (sort[0]["column_id"], sort[0].get("direction", "asc")) == default:
            d.pop("sort_by")
    return d


TABLES = [c for c in DATA["cases"] if OQO.from_dict(c["oqo"]).group_by]


@pytest.mark.parametrize("c", TABLES, ids=lambda c: f"{c['case']}-{c['shape']}")
def test_every_table_reads_get_the_numbers(c):
    text = render_core(OQO.from_dict(c["oqo"]), resolver)
    assert text.startswith("get the ") and " by " in text
    assert not text.startswith(("rank ", "break down "))


@pytest.mark.parametrize("c", TABLES, ids=lambda c: f"{c['case']}-{c['shape']}")
def test_a_table_means_what_it_meant(c):
    # the same query as the v3 sentence, up to the default order (never written)
    oqo = OQO.from_dict(c["oqo"])
    text = render_core(oqo, resolver)
    assert _without_default_order(parse(text)) == _without_default_order(oqo)
    assert render_core(parse(text), resolver) == text            # a fixed point


@pytest.mark.parametrize("old,new", [
    ("rank authors at [University of British Columbia](I141945490) by count of works about kelp",
     "get the count of works about kelp by author at [University of British Columbia](I141945490)"),
    ("break down works about kelp by year", "get the count and share of works about kelp by year"),
    ("rank institutions in [Sweden](SE) with at least 10 works about kelp by mean FWCI",
     "get the mean FWCI of works about kelp by institution in [Sweden](SE), highest first. "
     "Only institutions with at least 10 works about kelp."),
    ("rank countries by count of works about kelp. Show mean FWCI.",
     "get the count and mean FWCI of works about kelp by country"),
    ("rank authors by count of works about kelp. Show h-index.",
     "get the count of works about kelp by author. Show h-index."),
    ("break down works about kelp by year and country", "get the count and share of works about kelp by year and country"),
    ("get authors at [University of British Columbia](I141945490) with an h-index above 50, highest h-index first",
     "get authors at [University of British Columbia](I141945490) with an h-index above 50, highest h-index first"),
    ("rank authors at [University of British Columbia](I141945490) by h-index. Only authors with an h-index above 50.",
     "get authors at [University of British Columbia](I141945490) with an h-index above 50, highest h-index first"),
])
def test_rank_and_break_down_are_accepted_and_echo_the_table(old, new):
    assert render_core(parse(old), resolver) == new


BASE = "get the count and mean FWCI of works about kelp by author at [University of British Columbia](I141945490)"


@pytest.mark.parametrize("sort,tail", [
    (None, ""),
    (SortBy("count", "desc"), ""),
    (SortBy("count", "asc"), ", fewest works first"),
    (SortBy("mean_fwci", "desc"), ", highest mean FWCI first"),
    (SortBy("mean_fwci", "asc"), ", lowest mean FWCI first"),
    (SortBy("summary_stats_h_index", "desc"), ", highest h-index first"),
])
def test_a_sort_changes_only_the_ending(sort, tail):
    oqo = parse(BASE)
    if sort is not None:
        if sort.column_id == "summary_stats_h_index":
            oqo = parse(BASE + ". Show h-index.")
        oqo.sort_by = [sort]
    text = render_core(oqo, resolver)
    assert text == BASE + tail
    back = parse(text)
    assert [(s.column_id, s.direction) for s in back.sort_by] == \
        ([] if not tail else [(sort.column_id, sort.direction)])


@pytest.mark.parametrize("text", [
    "get the count of works about kelp by year",
    "get the count of works about kelp by year, most works first",
    "get the count of works about kelp by year, newest first",
    "get the count of works since 2020 in [Cureus](S2738950867) by country, alphabetical by country",
    "get the count and share of works about kelp by year and country in ([United States](US), [China](CN))",
    "get the percent retracted of works since 2006 by country, highest first. Only countries with more than "
    "100,000 works since 2006.",
    "get the count of works in [Nature](S137773608) by author. Show h-index.",
    "get the count of works in [IEEE/ACM International Conference on Software Engineering (ICSE)](S7407086679) "
    "by author with an h-index above 40",
    "get the count of works co-authored with [Kiel University](I32021983) by company",
    "get the count of works about kelp by year and institution in the collection [My peers](col_peers)",
    "get the sum of citations to works since 2018 about oleogel* by author, highest first",
    "get the count of works in the topic (T10091) by institution in [Africa](Q15)",
])
def test_fixed_points(text):
    import re
    names = {m.group(2): m.group(1) for m in re.finditer(r"\[([^\]]*)\]\(([^)]+)\)", text)}
    assert render_core(parse(text), lambda v, c=None: names.get(str(v))) == text


def test_share_is_the_word():
    assert render_core(parse("get the count and share of the total of all works by SDG"), resolver) == \
        "get the count and share of all works by SDG"


def test_highest_first_needs_one_number():
    with pytest.raises(Exception):
        parse_core("get the count and mean FWCI of works about kelp by country, highest first")


def test_an_only_over_other_works_is_refused():
    with pytest.raises(Exception):
        parse_core("get the count of works about kelp by country. Only countries with at least 5 works about cod.")


def test_a_count_floor_on_the_split_must_be_an_only_sentence():
    with pytest.raises(Exception):
        parse_core("get the count of works about kelp by country with at least 5 works about kelp")


@pytest.mark.parametrize("old,new", [
    # the things left out by their own ID (#1744's demo, B5 and B6)
    ("get countries where that country is not [Kenya](KE) that published works where country is [Kenya](KE); "
     "then, summarize each country using count",
     "get the count of works from [Kenya](KE) by country except [Kenya](KE)"),
    ("get institutions where that institution is not ([ETH Zurich](I35440088) or [Board of the Swiss Federal "
     "Institutes of Technology](I2799323385)) that published works where institution is [ETH Zurich](I35440088) "
     "and published since 2020; then, summarize each institution using count",
     "get the count of works since 2020 co-authored with [ETH Zurich](I35440088) by institution except "
     "([ETH Zurich](I35440088), [Board of the Swiss Federal Institutes of Technology](I2799323385))"),
    # works with every one of several places (B4)
    ("get works where institution is ([University of Oxford](I40120149) and [University of Cambridge](I241749)); "
     "then, group those works by year; finally, summarize using count",
     "get the count of works from both [University of Oxford](I40120149) and [University of Cambridge](I241749) "
     "by year"),
    ("get works where institution is ([University of Oxford](I40120149) and [University of Cambridge](I241749) "
     "and [Imperial College London](I47508984))",
     "get works from all of [University of Oxford](I40120149), [University of Cambridge](I241749), and "
     "[Imperial College London](I47508984)"),
])
def test_demo_forms(old, new):
    import re
    from query_translation.oql_parser import parse_either
    names = {m.group(2): m.group(1) for m in re.finditer(r"\[([^\]]*)\]\(([^)]+)\)", old)}
    res = lambda v, c=None: names.get(str(v))   # noqa: E731
    o = parse_either(old)
    o = canonicalize_oqo(o[0] if isinstance(o, tuple) else o, sort_operands=False)
    assert render_core(o, res) == new
    assert canonicalize_oqo(parse(new)).to_dict() == canonicalize_oqo(o).to_dict()


def test_other_than_reads_as_except():
    assert render_core(parse("rank countries other than [Kenya](KE) by count of works from [Kenya](KE)"), resolver) \
        == "get the count of works from [Kenya](KE) by country except [Kenya](KE)"
