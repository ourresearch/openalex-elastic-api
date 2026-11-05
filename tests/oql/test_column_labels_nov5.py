"""A table's column labels say what its sentence says (oxjob #1555, 2026-11-05).

`meta.measures[].oql` labels the website's table headers, chart legends, the connector's
columns and the CSV headers. It said `mean citation count`, `percent of those works` and
`percent has DOI` while the sentence above the table said `mean citations`, `share` and
`percent with a DOI`: one word per concept. A download's file name follows the sentence
too (it was the old general form's slug).
"""
import pytest

from query_translation import analytics as A
from query_translation.execution import _sort_column
from query_translation.oql_core import MEASURE_NAMES, render_core
from query_translation.oql_parser import parse_either
from query_translation.oqo import Measure

TABLE = ("get the count, share, mean citations, median citations, sum of citations, "
         "percent with a DOI, percent open access, and mean FWCI of works about kelp by country")


def _labels(oqo):
    return [A._measure_meta(m, oqo.get_rows)["oql"] for m in oqo.calculate]


def test_each_label_is_the_sentences_word():
    oqo = parse_either(TABLE)
    assert _labels(oqo) == ["count", "share", "mean citations", "median citations",
                            "sum of citations", "percent with a DOI", "percent open access",
                            "mean FWCI"]
    sentence = render_core(oqo)
    for label in _labels(oqo):
        assert label in sentence


@pytest.mark.parametrize("key", sorted(k for k in MEASURE_NAMES if k[0] not in ("count", "value")))
def test_every_named_number_labels_its_column_by_that_name(key):
    label = A._measure_meta(Measure(*key), "works")["oql"]
    assert label == {"share of the total": "share"}.get(MEASURE_NAMES[key], MEASURE_NAMES[key])


def test_a_number_with_no_sentence_name_keeps_its_field_words():
    assert A._measure_meta(Measure("min", "cited_by_count"), "works")["oql"] == "min citation count"
    assert A._measure_meta(Measure("sum", "fwci"), "works")["oql"] == "sum FWCI"


@pytest.mark.parametrize("word,key", [
    ("mean citations", "mean_cited_by_count"),          # the label
    ("mean citation count", "mean_cited_by_count"),     # the older words still sort
    ("mean_cited_by_count", "mean_cited_by_count"),     # the key
    ("share", "percent_of_those"),
    ("percent of those works", "percent_of_those"),
    ("percent with a DOI", "percent_has_doi"),
    ("percent has DOI", "percent_has_doi"),
])
def test_a_sort_reads_the_label_and_the_older_words(word, key):
    oqo = parse_either(TABLE)
    assert _sort_column(word, word, oqo) == key


# --- a download is named for the sentence ---------------------------------------------

@pytest.mark.parametrize("style,start", [
    ("core", "openalex-get-the-count-and-share-of-works-with-kelp-in-the-title-by-year"),
    ("pipeline", "openalex-get-works-where-title-has-kelp-then"),
])
def test_a_download_is_named_for_the_echo(style, start):
    from flask import Flask

    from query_translation import analytics_csv
    from query_translation.execution import _download_text
    oqo = parse_either("get works where title has kelp; then, group those works by year; "
                       "finally, summarize using count and percent of those works")
    with Flask(__name__).test_request_context(f"/?oql_style={style}"):
        name = analytics_csv.filename(_download_text(oqo))
    assert name.startswith(start)
