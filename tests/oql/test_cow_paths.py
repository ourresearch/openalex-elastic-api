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
