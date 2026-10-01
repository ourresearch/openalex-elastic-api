"""OQL words for the works author-position filters (oxjob #1474).

Each word parses to its column, renders back to the same word, and survives
OQO -> OQL -> OQO; the two-, three- and four-word names win over the shorter
`author`, `institution`, `country` and `author country` words they start with.

    PYTHONPATH=. venv/bin/python -m pytest tests/oql/test_author_position_words.py --noconftest -q
"""
import pytest

from tests.oql.oql_v2 import parse, render

CASES = [
    ("first author", "first_author_ids", "A5023888391", "A5023888391"),
    ("last author", "last_author_ids", "A5023888391", "A5023888391"),
    ("first author institution", "first_author_institution_ids", "I136199984", "I136199984"),
    ("last author institution", "last_author_institution_ids", "I136199984", "I136199984"),
    ("first author country", "first_author_countries", "us", "US"),
    ("last author country", "last_author_countries", "FR", "FR"),
]


@pytest.mark.parametrize("word,column,value,canonical", CASES)
def test_word_parses_and_round_trips(word, column, value, canonical):
    oqo = parse(f"works where {word} is {value}")
    rows = oqo.to_dict()["filter_rows"]
    assert rows == [{"column_id": column, "value": canonical}]
    oql = render(oqo)
    assert oql == f"works where {word} is ({canonical})"
    assert parse(oql).to_dict() == oqo.to_dict()


def test_last_author_with_first_author_institution():
    oqo = parse("works where last author is A5023888391 and first author institution is I136199984")
    assert [r["column_id"] for r in oqo.to_dict()["filter_rows"]] == [
        "last_author_ids", "first_author_institution_ids"]


@pytest.mark.parametrize("oql,column", [
    ("works where author country is US", "last_known_institutions.country_code"),
    ("works where corresponding author is A5023888391", "corresponding_author_ids"),
    ("works where first page is 12", "biblio.first_page"),
    ("works where last page is 12", "biblio.last_page"),
])
def test_neighbouring_words_unchanged(oql, column):
    assert parse(oql).to_dict()["filter_rows"][0]["column_id"] == column
