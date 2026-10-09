"""Thing-first (oxjob #1555, Jason 2026-10-09): start with the thing you want.

`get authors at [UBC](I141945490) since 2022 who published works where ...` is a split of
works by the thing with a filter on the thing's own record, written thing first. Every
split by a thing (authors, institutions, sources, publishers, funders, countries, topics)
echoes this way ("it's important to be consistent"); the old split form stays accepted.
The summary names what it summarizes: `summarize each author using ...` (one row per
author), `summarize all those works using ...` (one row for the set).
"""
import datetime

import pytest

from query_translation.diagnostics import OQLError
from query_translation.oql_lang import parse
from query_translation.oql_pipeline import render_pipeline_line
from query_translation.oqo import AffiliationFilter, MeasureFilter, OQO
from query_translation.oqo_canonicalizer import canonicalize_oqo
from query_translation.validator import validate_oqo

UBC = "[University of British Columbia](I141945490)"
DEFAULT_SINCE = datetime.date.today().year - 4     # the last five years


def _echo(q):
    return render_pipeline_line(canonicalize_oqo(parse(q), sort_operands=False))


def _same(a, b):
    return canonicalize_oqo(parse(a)).to_dict() == canonicalize_oqo(parse(b)).to_dict()


# (input, echo): the echo is a fixed point and means the same as the input
ECHOES = [
    (f"get authors at {UBC} since 2022 who published works where title-abstract has kelp; "
     "then, summarize each author using count and mean FWCI",
     "get authors at (I141945490) since 2022 who published works where title-abstract has (kelp); "
     "then, summarize each author using count and mean FWCI"),
    # a bare summary after a thing-first start is per thing
    (f"get authors at {UBC} now who published works where title-abstract has kelp; "
     "then, summarize using count and h-index",
     "get authors at (I141945490) now who published works where title-abstract has (kelp); "
     "then, summarize each author using count and h-index"),
    (f"get authors ever at {UBC} who published works where title-abstract has kelp",
     "get authors ever at (I141945490) who published works where title-abstract has (kelp)"),
    (f"get authors at ({UBC} or [University of Victoria](I212119943)) from 2020 through 2024 "
     "who published works where title-abstract has kelp",
     "get authors at (I141945490 or I212119943) from 2020 through 2024 who published works "
     "where title-abstract has (kelp)"),
    (f"get authors at {UBC} in 2023 who published works where title has kelp",
     "get authors at (I141945490) in 2023 who published works where title has (kelp)"),
    ("get institutions in [Asia](Q48) that published works where topic is (T13294) and "
     "published since 2016; then, group each institution's works by year; finally, summarize "
     "using count",
     "get institutions in [Asia](Q48) that published works where topic is (T13294) and published "
     "since 2016; then, group each institution's works by year; finally, summarize using count"),
    ("get authors where h-index is above 20 who published more than 5 works where title has kelp",
     "get authors where h-index is above 20 who published more than 5 works where title has (kelp)"),
    ("get authors who published works where title has kelp; then, keep those authors where "
     "mean FWCI of those works is at least 2",
     "get authors who published works where title has (kelp); then, keep those authors where "
     "mean FWCI of those works is at least 2"),
    ("get funders that funded works where title has kelp; then, summarize each funder using count",
     "get funders that funded works where title has (kelp); then, summarize each funder using count"),
    ("get sources that published works where title has kelp",
     "get sources that published works where title has (kelp)"),
    ("get publishers that published works where title has kelp",
     "get publishers that published works where title has (kelp)"),
    ("get countries that published works where title has kelp",
     "get countries that published works where title has (kelp)"),
    ("get topics of works where institution is (I141945490)",
     "get topics of works where institution is (I141945490)"),
    # the old split reads thing-first
    ("get works where title has kelp; then group those works by author where count of those "
     "works > 10 and h-index > 20; then summarize using count",
     "get authors where h-index is above 20 who published more than 10 works where title has "
     "(kelp); then, summarize each author using count"),
    ("get works where title has kelp; then, group those works by institution and year",
     "get institutions that published works where title has (kelp); then, group each "
     "institution's works by year"),
    # a walk to the combined set, summarized, reads thing-first too
    ("get works where title has kelp; then, get authors of those works; then, summarize using count",
     "get authors who published works where title has (kelp); then, summarize all those authors "
     "using count"),
    # the summary names its scope
    ("get works where title has kelp; then, summarize using count",
     "get works where title has (kelp); then, summarize all those works using count"),
    ("get authors where h-index is above 20; then, summarize using count",
     "get authors where h-index is above 20; then, summarize all those authors using count"),
]


@pytest.mark.parametrize("q,echo", ECHOES)
def test_echo(q, echo):
    assert _echo(q) == echo
    assert _echo(echo) == echo
    assert _same(q, echo)
    assert validate_oqo(parse(q)).valid


def test_the_thing_first_oqo_is_a_split_with_the_things_own_record():
    o = parse(f"get authors at {UBC} since 2022 who published works where title-abstract has kelp")
    assert o.get_rows == "works"
    assert o.filter_rows[0].column_id == "title_and_abstract.search"
    g = o.group_by[0]
    assert g.column_id == "authorships.author.id"
    assert g.where == AffiliationFilter("affiliations.institution.lineage", "I141945490", since=2022)
    assert _same(f"get authors at {UBC} since 2022 who published works where title-abstract has kelp",
                 "get works where title-abstract has kelp; then, group those works by author")\
        is False


def test_at_with_no_years_is_the_last_five_years_written_out():
    echo = _echo(f"get authors at {UBC} who published works where title has kelp")
    assert f"at (I141945490) since {DEFAULT_SINCE} who published" in echo


@pytest.mark.parametrize("words,since,through", [
    ("since 2021", 2021, None), ("in 2023", 2023, 2023), ("from 2019 through 2022", 2019, 2022),
    ("through 2015", None, 2015), ("before 2015", None, 2014), ("after 2015", 2016, None),
    ("in the last 3 years", datetime.date.today().year - 2, None),
])
def test_at_years(words, since, through):
    o = parse(f"get authors at {UBC} {words} who published works where title has kelp")
    w = o.group_by[0].where
    assert (w.since, w.through) == (since, through)


def test_authors_in_a_country_read_their_record():
    o = parse("get authors in [Brazil](BR) since 2020 who published works where topic is (T10166)")
    assert o.group_by[0].where == AffiliationFilter("affiliations.institution.country_code", "BR",
                                                    since=2020)
    o = parse("get authors in [Brazil](BR) now who published works where topic is (T10166)")
    assert o.group_by[0].where.column_id == "last_known_institutions.country_code"


@pytest.mark.parametrize("q", [
    # what writers and readers reach for: any verb, `with`, `of`, the works from anywhere
    f"get authors at {UBC} since 2022 who published works at any institution in any year where title has kelp",
    f"get authors at {UBC} since 2022 who published works anywhere where title has kelp",
    f"get authors at {UBC} since 2022 who published works (at any institution, in any year) where title has kelp",
    f"get authors at {UBC} since 2022 who ever published works where title has kelp",
    f"get authors at {UBC} since 2022 with works where title has kelp",
    f"get authors at {UBC} since 2022 that wrote works where title has kelp",
])
def test_accepted_input(q):
    assert _same(q, f"get authors at {UBC} since 2022 who published works where title has kelp")


def test_count_words():
    for words, op, n in (("more than 5", ">", 5), ("at least 5", ">=", 5),
                         ("fewer than 3", "<", 3), ("at most 3", "<=", 3)):
        o = parse(f"get authors who published {words} works where title has kelp")
        assert o.group_by[0].where == MeasureFilter("count", op, n)


def test_summarize_all_those_authors_is_the_combined_set():
    o = parse("get authors who published works where title has kelp; then, summarize all those "
              "authors using count")
    assert not o.group_by
    assert o.walks[0].column_id == "authorships.author.id" and not o.walks[0].each
    assert o.walks[0].where is None


def test_keep_adds_to_the_things_conditions():
    o = parse("get authors where h-index is above 20 who published works where title has kelp; "
              "then, keep those authors where count of those works is above 5")
    parts = o.group_by[0].where.filters
    assert [type(p).__name__ for p in parts] == ["LeafFilter", "MeasureFilter"]


@pytest.mark.parametrize("q,code", [
    ("get topics at (I141945490) of works where title has kelp", "OQL_THING_PLACE"),
    ("get works where title has kelp; then, summarize each author using count", "OQL_SUMMARY_SCOPE"),
    ("get authors who published works where title has kelp; then, summarize all those works "
     "using count", "OQL_SUMMARY_SCOPE"),
    ("get authors who published more than 5 works where title has kelp; then, summarize all "
     "those authors using count", "OQL_SUMMARY_SCOPE"),
    ("get works where title has kelp; then, keep those authors where h-index is above 20",
     "OQL_KEEP_NEEDS_THINGS"),
])
def test_loud_errors(q, code):
    with pytest.raises(OQLError) as e:
        parse(q)
    assert e.value.code == code


def test_plain_starts_are_unchanged():
    # no `works` after a verb: the things' own list, as always
    o = parse("get authors where h-index is above 20")
    assert o.get_rows == "authors" and not o.group_by
    o = parse("get sources where works count is above 1000")
    assert o.get_rows == "sources"
