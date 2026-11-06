"""A works `type` filter value must name a work type, or the API answers a JSON 400 (oxjob #1836).

Before, `type:zzz-not-a-type`, `type:book-section` (retired 29 Jun 2026) and `type:journal-article`
(Crossref's label) each answered a count of 0 with no message.
"""
import pytest
from elasticsearch_dsl import Search

from core.exceptions import APIQueryParamsError
from core.filter import filter_records
from core.work_type_values import suggested_type, unknown_type_message, work_types
from works.fields import fields_dict


def _filter(value):
    return filter_records(fields_dict, [{"type": value}], Search()).to_dict()


def _error(value):
    with pytest.raises(APIQueryParamsError) as err:
        _filter(value)
    return str(err.value)


def test_the_list_is_the_24_live_types():
    assert len(work_types()) == 24
    assert {"article", "software-paper", "data-paper", "conference-paper"} <= set(work_types())
    assert "libguides" not in work_types()  # retired 7 Nov 2026 (oxjob #1647)


@pytest.mark.parametrize("value", [
    "article", "Article", "software-paper", "article|review", "!paratext", "!paratext|erratum",
    "types/article", "https://openalex.org/types/article", "https://openalex.org/work-types/book",
    "null", "!null", "article|null", '"article"',
])
def test_work_types_filter_as_before(value):
    assert _filter(value)


def test_an_unknown_type_names_the_list():
    msg = _error("zzz-not-a-type")
    assert msg.startswith("'zzz-not-a-type' is not a work type.")
    assert "article, book, book-chapter" in msg and "software-paper" in msg  # sorted
    assert "https://api.openalex.org/types" in msg


@pytest.mark.parametrize("value", ["article|zzz", "!zzz", "!article|zzz", "article zzz"])
def test_an_unknown_type_in_an_or_list_negation_or_and_list_is_caught(value):
    assert "'zzz' is not a work type." in _error(value)


@pytest.mark.parametrize("value,use", [
    ("book-section", "reference-entry"), ("database", "dataset"), ("report-component", "report"),
])
def test_a_retired_type_names_its_replacement(value, use):
    msg = _error(value)
    assert "no longer a work type (removed 29 Jun 2026)" in msg
    assert f"Use type:{use}." in msg


def test_grant_points_to_awards():
    assert "https://api.openalex.org/awards" in _error("grant")


# Library guides left OpenAlex on 7 Nov 2026, and their type with them (oxjob #1647).
@pytest.mark.parametrize("value", [
    "libguides", "LibGuides", "types/libguides", "https://openalex.org/types/libguides",
    "article|libguides", "!libguides", "!article|libguides", "article libguides", '"libguides"',
])
def test_libguides_is_retired_because_library_guides_are_not_scholarly(value):
    msg = _error(value)
    assert msg.startswith("'libguides' is no longer a work type (removed 7 Nov 2026): library guides "
                          "aren't scholarly works, so OpenAlex no longer includes them.")
    assert "Use type:" not in msg and "Did you mean" not in msg  # nothing replaced it
    assert "article, book, book-chapter" in msg and "libguides," not in msg


def test_a_crossref_label_names_the_type_and_the_raw_type_filter():
    msg = _error("journal-article")
    assert "Use type:article, or primary_location.raw_type:journal-article" in msg
    assert "Use type:conference-paper" in _error("proceedings-article")


def test_a_source_type_points_to_the_source_type_filter():
    assert "use primary_location.source.type:journal" in _error("journal")


@pytest.mark.parametrize("value,guess", [
    ("artcle", "article"), ("book_chapter", "book-chapter"), ("preprints", "preprint"),
    ("conference-papers", "conference-paper"),
])
def test_a_typo_gets_a_did_you_mean(value, guess):
    assert f"Did you mean type:{guess}?" in _error(value)


def test_suggested_type_feeds_oql_fix_its():
    assert suggested_type("journal-article") == "article"
    assert suggested_type("book-section") == "reference-entry"
    assert suggested_type("grant") is None
    assert suggested_type("libguides") is None
    assert suggested_type("journal") is None
    assert suggested_type("zzzzzz") is None


def test_only_the_works_type_filter_is_checked():
    # raw_type holds a source's own label: any value, never a work-type check
    filter_records(fields_dict, [{"primary_location.raw_type": "journal-article"}], Search())
    assert unknown_type_message("article") is None


def test_type_crossref_is_refused_and_points_to_raw_type():
    # empty on every work, so every value answered a silent 0
    with pytest.raises(APIQueryParamsError) as err:
        filter_records(fields_dict, [{"type_crossref": "journal-article"}], Search())
    assert "primary_location.raw_type:journal-article" in str(err.value)
