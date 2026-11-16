"""Two count mismatches from oxjob #1035's tickets (15 Nov 2026). No ES, no app.

1. ZD 5246: `primary_location.source.type:ebook platform` answered 0 while group_by listed 808,814
   ebook-platform works for 2024. A space in a filter value means AND, so the API asked for works
   whose source type is both `ebook` and `platform`. A two-word source type is now one value.
2. ZD 4463: paging a `title_and_abstract.search` by relevance repeated a work on one page and never
   showed another (316 rows, 315 distinct), because that filter didn't pin shard routing, so pages
   were scored on different shard copies. Every lexical search filter pins it now.
"""
import pytest
from elasticsearch_dsl import Search

from core.exceptions import APIQueryParamsError
from core.filter import filter_records
from core.preference import PREFERENCE_SEARCH_FILTERS, clean_preference, set_preference_for_filter_search
from institutions.fields import fields_dict as institutions_fields
from sources.fields import fields_dict as sources_fields
from works.fields import fields_dict as works_fields


def _q(fields, key, value):
    return filter_records(fields, [{key: value}], Search()).to_dict()


# ---------- 1. two-word source types ----------

@pytest.mark.parametrize("key", ["primary_location.source.type", "locations.source.type",
                                 "best_oa_location.source.type"])
@pytest.mark.parametrize("plain, quoted", [
    ("ebook platform", '"ebook platform"'),
    ("book series", '"book series"'),
    ("Ebook Platform", '"Ebook Platform"'),
    ("!ebook platform", '!"ebook platform"'),
    ("source-types/ebook platform", '"source-types/ebook platform"'),
    ("https://openalex.org/source-types/book series", '"https://openalex.org/source-types/book series"'),
])
def test_a_two_word_source_type_is_one_value(key, plain, quoted):
    assert _q(works_fields, key, plain) == _q(works_fields, key, quoted)


def test_it_is_a_single_term_not_an_and_of_its_words():
    q = _q(works_fields, "primary_location.source.type", "ebook platform")
    assert "ebook platform" in str(q)
    assert "'must'" not in str(q)


def test_the_group_by_key_form_matches_the_same_works():
    # group_by's key is source-types/ebook%20platform; its value round-trips as before
    assert _q(works_fields, "primary_location.source.type", "source-types/ebook%20platform") == \
        _q(works_fields, "primary_location.source.type", "ebook platform")


def test_sources_type_filter_reads_it_as_one_value_too():
    assert _q(sources_fields, "type", "ebook platform") == _q(sources_fields, "type", '"ebook platform"')


def test_works_type_with_a_source_type_names_the_filter_that_works():
    with pytest.raises(APIQueryParamsError) as err:
        _q(works_fields, "type", "ebook platform")
    assert "primary_location.source.type:ebook platform" in str(err.value)


@pytest.mark.parametrize("value", ["journal repository", "ebook platform journal"])
def test_other_spaced_values_keep_their_and_meaning(value):
    q = _q(works_fields, "locations.source.type", value)
    assert "'must'" in str(q)


def test_an_or_list_with_a_two_word_type_is_unchanged():
    q = _q(works_fields, "primary_location.source.type", "ebook platform|journal")
    assert q == _q(works_fields, "primary_location.source.type", '"ebook platform"|journal')


def test_an_institution_type_value_is_not_touched():
    assert _q(institutions_fields, "type", "education") == _q(institutions_fields, "type", '"education"')


# ---------- 2. shard routing for search filters ----------

@pytest.mark.parametrize("key", [
    "title_and_abstract.search", "title_and_abstract.search.exact", "fulltext.search",
    "title.search", "abstract.search", "default.search", "keyword.search",
    "title_abstract_keywords.search", "raw_author_name.search",
])
def test_lexical_search_filters_pin_shard_routing(key):
    s = set_preference_for_filter_search([{key: "kelp forest restoration"}], Search())
    assert s._params.get("preference") == clean_preference("kelp forest restoration")


def test_semantic_search_is_not_pinned():
    assert "semantic.search" not in PREFERENCE_SEARCH_FILTERS
    s = set_preference_for_filter_search([{"semantic.search": "kelp"}], Search())
    assert "preference" not in s._params


def test_every_works_lexical_search_filter_is_listed():
    lexical = {k for k in works_fields if ".search" in k and not k.startswith("semantic")}
    assert lexical <= set(PREFERENCE_SEARCH_FILTERS)
