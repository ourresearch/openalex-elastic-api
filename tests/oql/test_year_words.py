"""Years in words (oxjob #1555, Jason 2026-10-09: "published since 2020").

The echo writes a publication year's comparisons as words: `published since 2020`,
`published after 2020`, `published before 2020`, `published through 2024`, `published in
2023`, and an inclusive pair as `published from 2015 through 2024`. Every older form stays
accepted, and the generous input forms read the same (a reading test in EXPLORE.md
"Words for symbols" chose the wordings).
"""
import pytest

from query_translation.oql_lang import parse
from query_translation.oql_pipeline import render_pipeline_line
from query_translation.oqo_canonicalizer import canonicalize_oqo


def _canon(q):
    return canonicalize_oqo(parse(q)).to_dict()


def _echo(q):
    return render_pipeline_line(canonicalize_oqo(parse(q)))


ECHOES = [
    ("get works where title has kelp and year >= 2020", "get works where title has (kelp) and published since 2020"),
    ("get works where year > 2020", "get works where published after 2020"),
    ("get works where year < 2020", "get works where published before 2020"),
    ("get works where year <= 2024", "get works where published through 2024"),
    ("get works where year is 2023", "get works where published in 2023"),
    ("get works where year is (2019 or 2021)", "get works where published in (2019 or 2021)"),
    ("get works where year >= 2015 and year <= 2024", "get works where published from 2015 through 2024"),
    # a strict pair keeps two phrases, so the echo reads back to the same query
    ("get works where year > 2014 and year < 2025", "get works where published after 2014 and published before 2025"),
    # not every year comparison: a negation, a year that isn't four digits, other year fields
    ("get works where year is not 2020", "get works where year is not 2020"),
    ("get works where year > 42", "get works where year > 42"),
    ("get awards where start year >= 2020", "get awards where start year >= 2020"),
    # a compared range reads without parentheses
    ("get works where year > 2000; then compare (year >= 2010 and year <= 2014) versus (year >= 2015 and year <= 2019)",
     "get works where published after 2000; then, compare published from 2010 through 2014 versus "
     "published from 2015 through 2019"),
]


@pytest.mark.parametrize("q,echo", ECHOES)
def test_years_echo_in_words(q, echo):
    assert _echo(q) == echo
    assert _canon(echo) == _canon(q)


SAME = [
    ("get works where published since 2020", "get works where year >= 2020"),
    ("get works where published after 2020", "get works where year > 2020"),
    ("get works where published before 2020", "get works where year < 2020"),
    ("get works where published through 2024", "get works where year <= 2024"),
    ("get works where published until 2024", "get works where year <= 2024"),
    ("get works where published up to 2024", "get works where year <= 2024"),
    ("get works where published in 2023", "get works where year is 2023"),
    ("get works where published in 2020 or later", "get works where year >= 2020"),
    ("get works where published in 2024 or earlier", "get works where year <= 2024"),
    ("get works where published from 2015 to 2024", "get works where year >= 2015 and year <= 2024"),
    ("get works where published between 2015 and 2024", "get works where year >= 2015 and year <= 2024"),
    # the field word with a word for the comparison
    ("get works where year since 2020", "get works where year >= 2020"),
    ("get works where title has kelp and year after 2020", "get works where title has kelp and year > 2020"),
    # a full date reads the publication date
    ("get works where published since 2021-06-01", "get works where date >= 2021-06-01"),
    ("get works where published on or after 2021-06-01", "get works where date >= 2021-06-01"),
    ("get works where published before 2021-06-01", "get works where date < 2021-06-01"),
    ("get works where published through 2021-06-30", "get works where date <= 2021-06-30"),
    # inside a comparison
    ("get works where year > 2000; then compare published since 2020 versus published before 2010",
     "get works where year > 2000; then compare year >= 2020 versus year < 2010"),
]


@pytest.mark.parametrize("words,symbols", SAME)
def test_words_read_like_the_symbols(words, symbols):
    assert _canon(words) == _canon(symbols)


@pytest.mark.parametrize("q", [
    'get works where title has (published since) and year > 2000',
    'get works where title has "published after"',
])
def test_published_inside_a_search_stays_a_search(q):
    o = canonicalize_oqo(parse(q))
    leaves = [f for row in o.filter_rows for f in (getattr(row, "filters", None) or [row])]
    assert any(".search" in f.column_id and "published" in str(f.value) for f in leaves)


def test_compare_shorthand_after_a_published_phrase():
    assert _canon("get works where year > 2000; then compare published since 2020 versus 2010") == \
        _canon("get works where year > 2000; then compare year >= 2020 versus year >= 2010")


@pytest.mark.parametrize("q", [
    "get works where not year >= 2015",
    "get works where title has kelp and not citation count >= 5",
    "get works where not (citation count >= 5 and citation count <= 9)",
    "get works where not date >= 2021-01-01",
    "get works where not FWCI >= 1 and title has kelp",
])
def test_a_negated_comparison_keeps_its_not(q):
    """The echo dropped a comparison's `not` and read as the opposite query (live until
    2026-10-09). It writes the `not`, never a flipped operator: `not FWCI >= 1` also
    holds works with no FWCI."""
    o = canonicalize_oqo(parse(q))
    echo = render_pipeline_line(o)
    assert "not " in echo
    assert _canon(echo) == o.to_dict()


# Dates read like years (Jason 2026-10-09 13:26 CT), and the created date reads `added`.
DATE_ECHOES = [
    ("get works where date >= 2021-06-01", "get works where published since 2021-06-01"),
    ("get works where date <= 2021-06-30", "get works where published through 2021-06-30"),
    ("get works where date < 2021-06-01", "get works where published before 2021-06-01"),
    ("get works where date >= 2021-06-01 and date <= 2021-06-30",
     "get works where published from 2021-06-01 through 2021-06-30"),
    ("get works where created date >= 2025-01-01", "get works where added since 2025-01-01"),
    ("get works where created date >= 2025-01-01 and created date <= 2025-01-31",
     "get works where added from 2025-01-01 through 2025-01-31"),
    # a strict lower bound, an exact date, the updated date and a negation keep symbols
    ("get works where date > 2021-06-01", "get works where date > 2021-06-01"),
    ("get works where date is 2021-06-01", "get works where date is 2021-06-01"),
    ("get works where updated date >= 2025-01-01", "get works where updated date >= 2025-01-01"),
    ("get works where not date >= 2021-06-01", "get works where not date >= 2021-06-01"),
]


@pytest.mark.parametrize("q,echo", DATE_ECHOES)
def test_dates_echo_in_words(q, echo):
    assert _echo(q) == echo
    assert _canon(echo) == _canon(q)


@pytest.mark.parametrize("words,symbols", [
    ("get works where added since 2025-01-01", "get works where created date >= 2025-01-01"),
    ("get works where added on or after 2025-01-01", "get works where created date >= 2025-01-01"),
    ("get works where added between 2025-01-01 and 2025-01-31",
     "get works where created date >= 2025-01-01 and created date <= 2025-01-31"),
    ("get works where published from 2021-06-01 through 2021-06-30",
     "get works where date >= 2021-06-01 and date <= 2021-06-30"),
])
def test_date_words_read_like_the_symbols(words, symbols):
    assert _canon(words) == _canon(symbols)


@pytest.mark.parametrize("q,fix", [
    ("get works where published after 2021-06-01", "published since 2021-06-02"),
    ("get works where title has kelp and published after (2021-06-01)", "published since 2021-06-02"),
    ("get works where added after 2025-01-31", "added since 2025-02-01"),
    ("get works where date after 2021-06-01", "published since 2021-06-02"),
    ("get works where created date after 2025-01-31", "added since 2025-02-01"),
])
def test_after_a_date_is_ambiguous(q, fix):
    """Jason 2026-10-09: "after June 1st" may or may not include June 1, so the parser
    says so and offers both readings; years keep `after` (`published after 2020`)."""
    from query_translation.diagnostics import OQLError
    with pytest.raises(OQLError) as e:
        parse(q)
    assert e.value.code == "OQL_AMBIGUOUS_DATE" and fix in e.value.fixit
    assert _canon("get works where published after 2020") == _canon("get works where year > 2020")
