"""Forms Haiku reached for when writing OQL, now accepted (oxjob #1555, Jason 2026-10-08:
"let's pave the cow paths"). Each case: what Haiku wrote reads the same as the form we
already had. Rounds and counts: oxjob #1555 EXPLORE.md, "Cow paths".
"""
import pytest

from query_translation.oql_lang import parse
from query_translation.oql_pipeline import render_pipeline_line
from query_translation.oqo_canonicalizer import canonicalize_oqo


def _canon(q):
    return canonicalize_oqo(parse(q)).to_dict()


SAME = [
    # a yes/no field alone is true; `not` makes it false
    ("get works where has DOI and global south", "get works where has DOI is true and global south is true"),
    ("get works where not has DOI and type is article", "get works where has DOI is false and type is article"),
    ("get works where top 1% cited; then summarize using count",
     "get works where top 1% cited is true; then summarize using count"),
    # a closed vocabulary by name
    ("get works where continent is (Africa)", "get works where continent is (Q15)"),
    ('get works where country is ("United Kingdom" or Kenya)', "get works where country is (GB or KE)"),
    # `none` means no value
    ("get works where funder is not (none)", "get works where funder is not unknown"),
    # start from a saved list of works
    ("get works in (col_mylist); then group those works by year",
     "get works where openalex id is in (col_mylist); then group those works by year"),
    ("get works in the collection [My list](col_mylist) where year > 2020",
     "get works where openalex id is in (col_mylist) and year > 2020"),
    # more splits in one step
    ("get works where year > 2020; then group those works by author and by year",
     "get works where year > 2020; then group those works by author; then group those works again by year"),
    ("get works where year > 2020; then group those works by publisher then by year",
     "get works where year > 2020; then group those works by publisher; then group those works again by year"),
    # `IT` in a comparison is Italy, not the pronoun
    ("get works where year > 2020; then compare country (US) versus (IT)",
     "get works where year > 2020; then group those works by country in (US, IT)"),
]


@pytest.mark.parametrize("cow,road", SAME)
def test_cow_path_reads_like_the_road(cow, road):
    assert _canon(cow) == _canon(road)


def test_a_saved_list_of_works_echoes_as_a_start():
    echo = render_pipeline_line(canonicalize_oqo(parse("get works in (col_mylist) where year > 2020")))
    assert echo == "get works in the collection (col_mylist) where year > 2020"
    assert _canon(echo) == _canon("get works in (col_mylist) where year > 2020")


# Jason 2026-10-08: the splits read as one step, `by author and year` (no second `by`);
# `and by` after a group filter or bins; the Oxford comma for three. Either is accepted.
ECHOES = [
    ("get works where year > 2015; then group by author; then group again by year; then summarize using count",
     "get works where year > 2015; then, group those works by author and year; finally, summarize using count"),
    ("get works where year > 2015; then group those works by year and by type and by country",
     "get works where year > 2015; then, group those works by year, type, and country"),
    ("get works where title-abstract has kelp; then group by author where count of those works > 10; "
     "then group again by year",
     "get works where title-abstract has (kelp); then, group those works by author where count of those "
     "works > 10 and by year"),
    ("get works where year > 2015; then group those works into citation count bins at (1, 10); then group again by year",
     "get works where year > 2015; then, group those works into citation count bins at (1, 10) and by year"),
    ("get works where year > 2020; then compare type article versus review by year and by country",
     "get works where year > 2020; then, compare type [article](article) versus [review](review) by year and country"),
]


@pytest.mark.parametrize("q,echo", ECHOES)
def test_splits_read_as_one_step(q, echo):
    o = canonicalize_oqo(parse(q))
    assert render_pipeline_line(o) == echo
    assert _canon(echo) == o.to_dict()


# Round 2 (Haiku 5.5, 300 fresh questions, guide in today's echo)
SAME_R2 = [
    # the echo's own set form after another condition (was a parse error: a bug)
    ("get works where source type is [journal](journal) and it cites a work in the set (works where year > 2020)",
     "get works where source type is journal and it cites works in (get works where year > 2020)"),
    ("get works where institution is I63966007 and it doesn't cite any work in the set (works where year > 2020)",
     "get works where institution is I63966007 and it doesn't cite works in (get works where year > 2020)"),
    # a bare one-word wildcard is exact text, as if quoted
    ("get works where title-abstract has (adolescen* OR teen*)",
     'get works where title-abstract has ("adolescen*" OR "teen*")'),
    # `institution continent`, as `institution country`; `ID` for the OpenAlex id
    # (registry aliases, PROPERTIES_VERSION 15.1.0 on the branch, Jason's yes 2026-10-08)
    ("get works where institution continent is Q15", "get works where continent is Q15"),
    ("get works where ID is (W2741809807 or W2100837269)",
     "get works where openalex id is (W2741809807 or W2100837269)"),
    # a DOI keeps its parentheses
    ("get works where DOI is (10.1016/S0140-6736(20)30183-5 or 10.1056/NEJMoa2034577)",
     'get works where DOI is ("10.1016/S0140-6736(20)30183-5" or "10.1056/NEJMoa2034577")'),
]


@pytest.mark.parametrize("cow,road", SAME_R2)
def test_cow_path_round_2(cow, road):
    assert _canon(cow) == _canon(road)


def test_a_parenthesis_after_a_plain_word_is_still_a_group():
    assert _canon("get works where title has (sleep (REM) cycles)") == _canon(
        "get works where title has (sleep AND REM AND cycles)")


# Yes/no flags as sentences, the June 2026 phrasing, accepted again (Jason 2026-10-08:
# "accept either"); canonical stays `<flag> is true|false`.
SENTENCES = [
    ("get works where it's open access and it doesn't have a DOI",
     "get works where open access is true and has DOI is false"),
    ("get works where it has DOI", "get works where has DOI is true"),
    ("get works where it is not retracted", "get works where retracted is false"),
    ("get works where it isn't retracted", "get works where retracted is false"),
    ("get works where it has no abstract", "get works where has abstract is false"),
    ("get works where it's in the top 10% by citations", "get works where top 10% cited is true"),
    ("get works where year > 2020; then compare it's open access versus it isn't open access",
     "get works where year > 2020; then compare open access versus not open access"),
]


@pytest.mark.parametrize("sentence,road", SENTENCES)
def test_a_flag_as_a_sentence(sentence, road):
    assert _canon(sentence) == _canon(road)


def test_a_relation_still_reads_as_a_relation():
    # `it's cited by` is the relation, not a flag sentence
    assert _canon("get works where it's cited by (W2741809807)") != _canon("get works where has DOI is true")
    echo = render_pipeline_line(canonicalize_oqo(parse("get works where it cites (W2741809807)")))
    assert echo == "get works where it cites (W2741809807)"   # not ((W2741809807))


# After a plain value, a flag sentence, a flag alone, or `not <condition>` starts a new
# condition (each was read as a second value: the yes/no write test found it, 2026-10-08).
AFTER_A_VALUE = [
    ("get works where type is [article](article) and year is 2021 and it's not open access",
     "get works where type is article and year is 2021 and open access is false"),
    ("get works where type is article and has DOI and year is 2020",
     "get works where type is article and has DOI is true and year is 2020"),
    ("get works where country is [Ghana](GH) and not retracted",
     "get works where country is GH and retracted is false"),
    ("get works where type is article and not year is 2020",
     "get works where type is article and year is not 2020"),
]


@pytest.mark.parametrize("q,road", AFTER_A_VALUE)
def test_a_condition_after_a_plain_value(q, road):
    assert _canon(q) == _canon(road)
