"""Echo gaps fixed 2026-11-05 (oxjob #1555).

A bare link reads like a named one: a journal URL's echo `get works in (S137773608)` read
back as works listed by ID (a 400 on production), found by a sweep of every works filter's
echo (`work/scripts/nov5_echo_sweep.py` in the oxjob).

A table's column labels say what its sentence says.

`meta.measures[].oql` labels the website's table headers, chart legends, the connector's
columns and the CSV headers. It said `mean citation count`, `percent of those works` and
`percent has DOI` while the sentence above the table said `mean citations`, `share` and
`percent with a DOI`: one word per concept. A download's file name follows the sentence
too (it was the old general form's slug).
"""
import pytest

from query_translation import analytics as A
from query_translation.execution import _sort_column
from query_translation.diagnostics import OQLError
from query_translation.oql_core import MEASURE_NAMES, render_core
from query_translation.oql_parser import core_reason, parse_either
from query_translation.oqo import Measure
from query_translation.oqo_canonicalizer import canonicalize_oqo

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


# --- a bare link after `in` reads like a named one -------------------------------------

def _filters(text):
    return canonicalize_oqo(parse_either(text)).to_dict()["filter_rows"]


@pytest.mark.parametrize("url_filter", [
    "primary_location.source.id:S137773608",
    "primary_location.source.id:S137773608|S4210178049",
    "authorships.institutions.lineage:I63966007",
    "authorships.institutions.continent:Q15",
])
def test_a_url_filters_echo_reads_back_without_names(url_filter):
    from query_translation.url_parser import parse_url_to_oqo
    oqo = canonicalize_oqo(parse_url_to_oqo("works", filter_string=url_filter))
    echo = render_core(oqo)
    assert canonicalize_oqo(parse_either(echo)).to_dict() == oqo.to_dict()


def test_a_bare_journal_after_in_is_the_journal():
    assert _filters("get works in (S137773608)") == _filters("get works in [Nature](S137773608)")
    assert _filters("get works in (S137773608)") == [
        {"column_id": "primary_location.source.id", "value": "S137773608"}]


@pytest.mark.parametrize("text", [
    "get works in (W2741809807, W2100837269)",      # works listed by ID
    "get works in (col_LV29j8URoX)",                # a works collection
    "get works in (US)",                            # not a link to the sentence: unchanged
])
def test_works_ids_and_collections_after_in_are_unchanged(text):
    assert all("ids.openalex" in str(f) for f in _filters(text))


@pytest.mark.parametrize("split,column", [
    ("continent", "authorships.institutions.continent"),
    ("institution type", "authorships.institutions.type"),
    ("source type", "primary_location.source.type"),
    ("license", "primary_location.license"),
    ("keyword", "keywords.id"),
    ("global south", "authorships.institutions.is_global_south"),
])
def test_the_general_forms_splits_read_as_sentences(split, column):
    general = (f"get works where title has kelp; then, group those works by {split}; "
               "finally, summarize using count")
    oqo = canonicalize_oqo(parse_either(general))
    assert [g.column_id for g in oqo.group_by] == [column]
    sentence = render_core(oqo)
    assert sentence == f"get the count of works with kelp in the title by {split}"
    assert canonicalize_oqo(parse_either(sentence)).to_dict() == oqo.to_dict()


def test_a_new_split_pairs_with_year():
    oqo = canonicalize_oqo(parse_either("get the count and share of works about kelp by continent and year"))
    assert [g.column_id for g in oqo.group_by] == ["authorships.institutions.continent", "publication_year"]
    assert render_core(oqo) == "get the count and share of works about kelp by continent and year"


def test_a_bare_link_of_another_kind_gets_its_words():
    with pytest.raises(OQLError) as e:
        parse_either("get works in (A5023888391)")
    assert "by (A5023888391)" in core_reason(e.value.core_error)[1]
