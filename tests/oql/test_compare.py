"""The `compare` step (oxjob #1555, Jason 2026-10-08).

`get works where topic is [CRISPR](T10878); then, compare institution [MIT](I63966007)
versus [Stanford University](I97018004) by year; summarize using count`: the things
compared (one group each; the summary row is the whole set), breakdowns with `by`, and
the summary after a bare `;` (no `then` or `finally`). It replaces split lists
(`group those works by institution in (A, B)`) and named sets (`group those works into
(...)`), which stay accepted input and echo as `compare`. Underneath it is the same
split, so nothing new runs.
"""
import pytest

from query_translation.diagnostics import OQLError
from query_translation.oql_lang import parse
from query_translation.oql_pipeline import render_pipeline_line
from query_translation.oqo_canonicalizer import canonicalize_oqo


def _canon(q):
    return canonicalize_oqo(parse(q))


def _echo(q):
    return render_pipeline_line(_canon(q))


ECHOES = [
    # a split list (launch form) -> listed values of one field
    ("get works where topic is (T10878); then group those works by institution in "
     "(I63966007, I97018004, I136199984); then calculate count, mean FWCI, percent open access",
     "get works where topic is (T10878); then, compare institution (I63966007) versus "
     "(I97018004) versus (I136199984); summarize using count, mean FWCI, and percent "
     "open access"),
    # listed searches; a breakdown
    ('get works where year >= (2010); then group those works by title-abstract search in '
     '(("inference latency"), ("neuromorphic computing"), ("edge AI")); then group those '
     'works again by year; then calculate count',
     'get works where year >= 2010; then, compare title-abstract has "inference latency" '
     'versus "neuromorphic computing" versus "edge AI" by year; summarize using count'),
    # named sets on different fields: each names its field
    ("get works where year >= (2016); then group those works into ((institution is "
     "(I99464096)), (country is (BE))); then group those works again by SDG; then calculate "
     "count, percent of those works",
     "get works where year >= 2016; then, compare institution (I99464096) versus country "
     "[Belgium](BE) by SDG; summarize using count and percent of those works"),
    # a compound item takes parentheses; comparisons keep their verb
    ("get works where institution is in (col_abc123); then group those works into ((year >= "
     "(2016) and year <= (2019)), (year >= (2021))); then group those works again by topic; "
     "then calculate count",
     "get works where institution is in the collection (col_abc123); then, compare (year >= 2016 "
     "and year <= 2019) versus year >= 2021 by topic; summarize using count"),
    # a yes/no field alone is true; `not` makes it false
    ("get works where institution is I146416000 and year >= 2020; then compare open access "
     "versus not open access by field; summarize using count and median citation count",
     "get works where institution is (I146416000) and year >= 2020; then, compare open "
     "access versus not open access by field; summarize using count and median citation "
     "count"),
    # `and` inside an item is logic: papers with both countries
    ("get works where year >= 2015; then compare (country US and CN) versus (country US and "
     "GB) by year; summarize using count",
     "get works where year >= 2015; then, compare (country [China](CN) and [United States]"
     "(US)) versus (country [United Kingdom](GB) and [United States](US)) by year; summarize "
     "using count"),
    # long lists: a collection's members
    ("get works where topic is T10878; compare each institution in the collection "
     "[Our peers](col_abc123); summarize using count",
     "get works where topic is (T10878); then, compare each institution in the collection "
     "(col_abc123); summarize using count"),
    # a breakdown with a group filter, then another breakdown (`and by`)
    ("get works where title-abstract has kelp; then compare institution I63966007 versus "
     "I97018004 by author where count of those works > 10 and by year; summarize using count",
     "get works where title-abstract has (kelp); then, compare institution (I63966007) versus "
     "(I97018004) by author where count of those works > 10 and by year; summarize using "
     "count"),
    # a boolean search item keeps its parentheses; bins as a breakdown
    ("get works where year >= 2020; then compare title-abstract has (kelp OR seaweed) versus "
     '"sea grass" by citation count bins at (1, 10, 100); summarize using count',
     "get works where year >= 2020; then, compare title-abstract has (kelp OR seaweed) versus "
     '"sea grass" by citation count bins at (1, 10, 100); summarize using count'),
]


@pytest.mark.parametrize("q,echo", ECHOES)
def test_echo_and_round_trip(q, echo):
    o = _canon(q)
    assert o.uses_pipeline
    assert render_pipeline_line(o) == echo
    assert _canon(echo).to_dict() == o.to_dict()


def test_no_step_word_before_the_summary():
    echo = _echo("get works where topic is T10878; then compare institution I63966007 "
                 "versus I97018004; then calculate count")
    assert "; summarize using count" in echo
    assert "finally" not in echo


SAME = [
    # versus, vs, vs.
    ("get works where year > 2020; then compare type article versus review",
     "get works where year > 2020; then compare type article vs review",
     "get works where year > 2020; then compare type article vs. review"),
    # `is` unsaid or said; the field once or every time
    ("get works where year > 2020; then compare institution I1 versus I2",
     "get works where year > 2020; then compare institution is I1 versus institution is I2",
     "get works where year > 2020; then group those works by institution in (I1, I2)"),
    # the measures after `on`, or a summary after `;` with or without a step word
    ("get works where year > 2020; then compare type article versus review on count and "
     "mean FWCI by year",
     "get works where year > 2020; then compare type article versus review by year; "
     "summarize using count and mean FWCI",
     "get works where year > 2020; then compare type article versus review by year; then "
     "summarize using count, mean FWCI"),
    # `by` once for several breakdowns, or `and by`
    ("get works where year > 2020; then compare type article versus review by year and by "
     "country",
     "get works where year > 2020; then compare type article versus review by year and "
     "country",
     "get works where year > 2020; then compare type article versus review by year, by country"),
    # after a search, parentheses hold the next search
    ('get works where year > 2020; then compare title-abstract has "machine learning" '
     'versus ("edge AI" NOT cloud)',
     'get works where year > 2020; then group those works by title-abstract search in '
     '(("machine learning"), ("edge AI" NOT cloud))'),
    # ... unless a field opens them: then they hold a compound item
    ("get works where year > 2020; then compare title-abstract has kelp versus "
     "(title-abstract has seaweed and type is review)",
     "get works where year > 2020; then group those works into ((title-abstract has kelp), "
     "(title-abstract has seaweed and type is review))"),
    # a compound item with or without its parentheses (versus bounds it)
    ("get works where year > 2015; then compare (country US and CN) versus country GB",
     "get works where year > 2015; then compare country US and CN versus country GB",
     "get works where year > 2015; then group those works into ((country is (US and CN)), "
     "(country is (GB)))"),
]


@pytest.mark.parametrize("forms", SAME)
def test_spellings_parse_to_one_oqo(forms):
    first = _canon(forms[0]).to_dict()
    for f in forms[1:]:
        assert _canon(f).to_dict() == first, f


ERRORS = [
    ("get works where year > 2020; then compare type article", "OQL_COMPARE_NEEDS_TWO"),
    ("get works where year > 2020; then group those works by year; then compare type "
     "article versus review", "OQL_COMPARE_AFTER_SPLIT"),
    ("get works where year > 2020; then compare each institution in (I1, I2)",
     "OQL_BAD_COMPARE"),
    ("get works where year > 2020; then compare type article versus review on count on "
     "count", "OQL_BAD_COMPARE"),
    ("get works where year > 2020; then compare type article versus review by year by "
     "country by funder", "OQL_TOO_MANY_SPLITS"),
    # splits divide works: no comparing authors (start or walk)
    ("get authors where h-index > 20; then compare last known institution I1 versus I2",
     "OQL_SPLIT_NEEDS_WORKS"),
    ("get works where year > 2020; then get authors of those works; then compare h-index > "
     "20 versus h-index <= 20", "OQL_SPLIT_NEEDS_WORKS"),
]


@pytest.mark.parametrize("q,code", ERRORS)
def test_errors(q, code):
    with pytest.raises(OQLError) as e:
        parse(q)
    assert e.value.code == code
