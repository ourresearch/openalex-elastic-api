"""oxjob #2645: Thai words inside a title, and formulas written with sub/superscript digits.

Thai writes no spaces between words and the standard tokenizer keeps each space-delimited run as one token, so
`title.search:ตัวตน` missed a title holding it inside a longer run. A works search holding Thai script now also
runs on the `.thai` / `.thai_exact` sub-fields (dictionary-cut by Elasticsearch's thai tokenizer, works-v42 on),
ORed in a dis_max. Sub/superscript digits are read by the works-v42 analyzers; the API only lets a typed `CO₂`
also find the split "CO 2" spelling (formula variant).
No ES: the keyword lookup is stubbed.
"""
import json

import pytest

from core.search import SearchOpenAlex, full_search_query, normalize_search_input, scoped_search_query


@pytest.fixture(autouse=True)
def no_keyword_lookup(monkeypatch):
    import core.keyword_search as ks
    monkeypatch.setattr(ks, "lookup", lambda spans: {s: [] for s in spans})
    ks.keyword_record.cache_clear()
    yield
    ks.keyword_record.cache_clear()


def _dump(q):
    return json.dumps(q.to_dict(), ensure_ascii=False)


def test_title_search_reads_thai_subfields():
    body = _dump(scoped_search_query("ตัวตน", "title", "default", skip_citation_boost=True))
    assert '"display_name.thai"' in body and '"alternate_titles.thai"' in body
    assert "abstract.thai" not in body and "thai_exact" not in body


def test_exact_door_reads_the_unstemmed_twin():
    body = _dump(scoped_search_query("ตัวตน", "title", "exact", skip_citation_boost=True))
    assert '"display_name.thai_exact"' in body and '"alternate_titles.thai_exact"' in body
    assert '"display_name.thai"' not in body


def test_title_and_abstract_reads_both_thai_subfields():
    body = _dump(scoped_search_query("การศึกษา AND การพัฒนา", "title_and_abstract", "default", skip_citation_boost=True))
    assert '"display_name.thai"' in body and '"abstract.thai^0.1"' in body


def test_default_search_keeps_its_three_fields_in_the_variant():
    s = SearchOpenAlex("การศึกษา COVID-19", secondary_field="abstract", tertiary_field="fulltext",
                       combine_fields=True, alternate_titles=True)
    v = s.thai_words_search()
    assert (v.primary_field, v.secondary_field, v.tertiary_field) == ("display_name.thai", "abstract.thai", "fulltext.thai")
    assert v._title_weight() == s._title_weight()
    body = _dump(full_search_query("works", "การศึกษา COVID-19", skip_citation_boost=True))
    assert '"fulltext.thai' in body and '"fulltext' in body


def test_fulltext_search_has_a_variant():
    s = SearchOpenAlex("การศึกษา", primary_field="fulltext", works_text=True, alternate_titles=True)
    assert s.thai_words_search().primary_field == "fulltext.thai"


@pytest.mark.parametrize("terms", ["climate change", "中国经济", "한국어 연구", "CO2"])
def test_no_thai_no_variant(terms):
    assert ".thai" not in _dump(full_search_query("works", terms, skip_citation_boost=True))
    assert ".thai" not in _dump(scoped_search_query(terms, "title", "default", skip_citation_boost=True))


def test_other_indexes_never_read_thai_subfields():
    for index in ("authors", "institutions", "sources", "topics"):
        assert ".thai" not in _dump(full_search_query(index, "การศึกษา", skip_citation_boost=True))


def test_variant_is_built_once():
    s = SearchOpenAlex("การศึกษา", primary_field="display_name", works_text=True, alternate_titles=True)
    v = s.thai_words_search()
    assert v.primary_field == "display_name.thai" and v.thai_words_search() is None
    assert _dump(s.build_query(skip_citation_boost=True)).count('"display_name.thai"') == 2  # match + match_phrase


def test_whole_query_not_drops_a_work_holding_the_word_in_either_form():
    s = SearchOpenAlex("NOT การศึกษา", primary_field="display_name", works_text=True, alternate_titles=True)
    assert s.thai_words_search() is None
    q = s.build_query(skip_citation_boost=True).to_dict()
    must_not = json.dumps(q["bool"]["must_not"], ensure_ascii=False)
    assert '"display_name.thai"' in must_not and '"display_name"' in must_not


def test_quoted_stop_word_phrase_uses_the_exact_twin():
    s = SearchOpenAlex('"vitamin a การศึกษา"', primary_field="display_name", works_text=True, alternate_titles=True)
    assert s._quote_kwargs() == {"quote_field_suffix": ".no_stem"}
    assert s.thai_words_search()._quote_kwargs() == {"quote_field_suffix": "_exact"}


def test_glyph_digits_reach_the_index_as_typed():
    # the works-v42 analyzers read them; the API leaves the text alone
    assert normalize_search_input("CO₂ Ca²⁺") == "CO₂ Ca²⁺"


@pytest.mark.parametrize("typed, variant", [("CO₂ capture", '"CO 2" capture'), ("Fe₃O₄", '"Fe 3 O 4"'), ("PM₂.₅", '"PM 2.5"')])
def test_formula_variant_reads_glyph_digits(typed, variant):
    v = SearchOpenAlex(typed, primary_field="display_name").formula_split_spelling()
    assert v is not None and v.search_terms == variant
