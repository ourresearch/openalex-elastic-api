"""oxjob #1882: a search with an in-word apostrophe also finds titles written with `’`.

The works index keeps a title's own glyph inside its token (`hartmann’s`), while
normalize_search_input makes every typed `’` a straight `'`. So 4.4M works with a curly
apostrophe in the title were found by none of those words, even by their own pasted
title. build_query now ORs (dis_max) in the `’` spelling. Not under NOT, not on semantic
search. No ES: the keyword lookup is stubbed.
"""
import json

import pytest

from core.search import SearchOpenAlex, full_search_query


@pytest.fixture(autouse=True)
def no_keyword_lookup(monkeypatch):
    import core.keyword_search as ks
    monkeypatch.setattr(ks, "lookup", lambda spans: {s: [] for s in spans})
    ks.keyword_record.cache_clear()
    yield
    ks.keyword_record.cache_clear()


def _dump(q):
    return json.dumps(q.to_dict(), ensure_ascii=False)


@pytest.mark.parametrize("typed", ["Hartmann's procedure", "Hartmann’s procedure"])
def test_either_glyph_searches_both_spellings(typed):
    s = SearchOpenAlex(search_terms=typed, primary_field="display_name")
    assert s.search_terms == "Hartmann's procedure"  # normalized as before
    variant = s.curly_apostrophe_spelling()
    assert variant is not None and variant.search_terms == "Hartmann’s procedure"
    body = _dump(s.build_query(skip_citation_boost=True))
    assert '"dis_max"' in body
    assert "Hartmann's procedure" in body and "Hartmann’s procedure" in body


def test_works_search_carries_both_spellings():
    body = _dump(full_search_query("works", "London's West End"))
    assert "London's West End" in body and "London’s West End" in body


@pytest.mark.parametrize(
    "terms",
    [
        "machine learning",  # no apostrophe
        "'quoted' words",  # apostrophes only at word edges: no token keeps them
        "alzheimer's NOT parkinson's",  # OR-ing spellings under NOT lets one through
    ],
)
def test_no_variant(terms):
    s = SearchOpenAlex(search_terms=terms, primary_field="display_name")
    assert s.curly_apostrophe_spelling() is None
    assert '"dis_max"' not in _dump(s.build_query(skip_citation_boost=True))


def test_whole_query_not_excludes_both_spellings():
    # `NOT x` is built as the complement of x's own query, so both spellings are excluded.
    s = SearchOpenAlex(search_terms="NOT alzheimer's", primary_field="display_name")
    assert s.curly_apostrophe_spelling() is None
    must_not = s.build_query(skip_citation_boost=True).to_dict()["bool"]["must_not"]
    body = json.dumps(must_not, ensure_ascii=False)
    assert "alzheimer's" in body and "alzheimer’s" in body


def test_semantic_search_has_no_variant():
    s = SearchOpenAlex(search_terms="children's health", is_semantic_query=True)
    assert s.curly_apostrophe_spelling() is None
