"""OQL reads a pasted title's `?` the way the URL search does (oxjob #1327).

In a run of 2+ bare words or a quoted multi-word phrase, a `?` that ends a word or stands
alone is a question mark. Before, `get works with (Should we ditch impact factors?) in the
title` was refused ("wildcards run on exact (no-stem) text ... quote it"), and quoting it
made the `?` a wildcard that misses the title; the URL echo of a quoted `search=` title
rendered `stemmed "...?"`, which OQL then refused. Unchanged: one word keeps a word-final
`?` as a wildcard (`psoriati?`, quoted or bare: #570, #1555), and a `?` inside a word
(`wom?n`) is a wildcard.
"""
import pytest

from query_translation.oql_parser import parse_oql_to_oqo as parse


def _rows(q):
    return parse(q).to_dict()["filter_rows"]


@pytest.mark.parametrize(
    "oql, column, value",
    [
        ("get works with (Should we ditch impact factors?) in the title",
         "display_name.search", "Should we ditch impact factors"),
        ('get works with (stemmed "Should we ditch impact factors?") in the title',
         "display_name.search", '"Should we ditch impact factors"'),
        ('get works with ("Should we ditch impact factors?") in the title',
         "display_name.search.exact", '"Should we ditch impact factors"'),
        ("get works with (Plus libres sans les garçons ? Une analyse) in the title",
         "display_name.search", "Plus libres sans les garçons Une analyse"),
        ("get works with (Mehr Demokratie durch Volksentscheid?) in the full text",
         "fulltext.search", "Mehr Demokratie durch Volksentscheid"),
    ],
)
def test_a_titles_question_mark_is_punctuation(oql, column, value):
    assert _rows(oql) == [{"column_id": column, "value": value, "operator": "has"}]


def test_stemmed_title_reads_the_same_as_without_the_mark():
    assert _rows("get works with (Is beautiful really usable?) in the title") == _rows(
        "get works with (Is beautiful really usable) in the title"
    )


@pytest.mark.parametrize(
    "oql, value",
    [
        ("get works with (psoriati?) in the title", "psoriati?"),
        ('get works with ("psoriati?") in the title', "psoriati?"),
        ("get works with (wom?n) in the title", "wom?n"),
    ],
)
def test_one_word_keeps_its_wildcard(oql, value):
    assert _rows(oql) == [{"column_id": "display_name.search.exact", "value": value, "operator": "has"}]


def test_a_wildcard_inside_a_word_in_stemmed_text_still_needs_quotes():
    with pytest.raises(Exception, match="exact"):
        parse("get works with (wom?n in science) in the title")


def test_a_leading_wildcard_on_one_bare_word_is_still_refused():
    with pytest.raises(Exception, match="leading wildcard"):
        parse("get works with (?cycle) in the title")
