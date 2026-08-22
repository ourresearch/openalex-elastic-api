"""Whole-query negation `NOT <operand>` in search values (oxjob #857).

A leading NOT used to fall through to the plain `match` branch, where the
English analyzer dropped `not` as a stopword and the POSITIVE query ran
(`search.title=NOT dog` returned the 108K dog papers). Now the engine builds
the positive query and takes its complement. These tests assert the emitted
ES query shape via `.to_dict()` — no ES needed.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

sys.modules["settings"] = type(sys)("settings")
sys.modules["settings"].ES_URL_WALDEN = "http://localhost:9200"

from core.search import SearchOpenAlex, full_search_query_exact, scoped_search_query
from core.search_negation import (
    has_leading_not,
    is_single_operand,
    whole_query_negation_operand,
)


def _build(value, **kw):
    return SearchOpenAlex(search_terms=value, **kw).build_query(
        skip_citation_boost=True
    ).to_dict()


def _complement_of(d):
    """Unwrap the `bool(must=[match_all], must_not=[positive])` shape; return
    the positive query dict."""
    assert set(d) == {"bool"}, d
    b = d["bool"]
    assert b["must"] == [{"match_all": {}}]
    assert len(b["must_not"]) == 1
    return b["must_not"][0]


# ---- detector -------------------------------------------------------------

@pytest.mark.parametrize("value,operand", [
    ("NOT dog", "dog"),
    ("  NOT   dog ", "dog"),
    ("(NOT dog)", "dog"),
    ('NOT "dog food"', '"dog food"'),
    ('NOT "dog food"~3', '"dog food"~3'),
    ("NOT (dog OR cat)", "(dog OR cat)"),
    ("NOT (dog cat)", "(dog cat)"),
    ("NOT dog*", "dog*"),
    ("NOT covid-19", "covid-19"),
])
def test_whole_query_negation_detected(value, operand):
    assert whole_query_negation_operand(value) == operand


@pytest.mark.parametrize("value", [
    "dog",                 # no NOT
    "dog NOT cat",         # NOT between terms: Lucene path, untouched
    "not dog",             # lowercase is a word
    "NOTHING dog",         # whole word only
    "notable dogs",
    '"NOT dog"',           # quoted phrase
    "-dog",                # #633: leading `-` is literal text
    "NOT",                 # bare operator, nothing to negate
    "NOT dog cat",         # two operands: Lucene modifier semantics (-dog +cat)
    "NOT dog AND cat",
    "NOT (dog) AND cat",   # paren group does NOT enclose the whole rest
    "(NOT dog) AND cat",
    'NOT "dog" "cat"',
])
def test_not_whole_query_negation(value):
    assert whole_query_negation_operand(value) is None


def test_is_single_operand_shapes():
    assert is_single_operand("dog")
    assert is_single_operand('"dog food"')
    assert is_single_operand("(dog OR cat)")
    assert is_single_operand('("dog food" OR cat)')
    assert not is_single_operand("dog cat")
    assert not is_single_operand("(dog) (cat)")
    assert not is_single_operand("")


def test_has_leading_not_requires_an_operand():
    assert has_leading_not("NOT dog cat")
    assert not has_leading_not("NOT")
    assert not has_leading_not("dog NOT cat")


# ---- engine: every door complements its own positive query ---------------

def test_single_field_complement_equals_positive_wrapped():
    positive = _build("dog", primary_field="display_name")
    assert _complement_of(_build("NOT dog", primary_field="display_name")) == positive
    # and the positive half is the analyzed plain branch (match | match_phrase),
    # not a query_string — exactly what `dog` alone builds.
    assert "match" in str(positive) and "query_string" not in str(positive)


def test_exact_single_field_complement():
    positive = _build("dog", primary_field="display_name.no_stem")
    assert _complement_of(_build("NOT dog", primary_field="display_name.no_stem")) == positive


def test_cross_field_title_and_abstract_complement():
    # The cross-field door ORs per-field clauses in its plain branch; the
    # complement must wrap the WHOLE positive query, never distribute into it.
    positive = scoped_search_query("dog", "title_and_abstract", "default",
                                   skip_citation_boost=True).to_dict()
    negated = scoped_search_query("NOT dog", "title_and_abstract", "default",
                                  skip_citation_boost=True).to_dict()
    assert _complement_of(negated) == positive


def test_cross_field_exact_complement():
    positive = scoped_search_query("dog", "title_and_abstract", "exact",
                                   skip_citation_boost=True).to_dict()
    negated = scoped_search_query("NOT dog", "title_and_abstract", "exact",
                                  skip_citation_boost=True).to_dict()
    assert _complement_of(negated) == positive


def test_full_exact_three_field_complement():
    positive = full_search_query_exact("dog", skip_citation_boost=True).to_dict()
    negated = full_search_query_exact("NOT dog", skip_citation_boost=True).to_dict()
    assert _complement_of(negated) == positive


def test_phrase_and_group_operands_complement_their_positive():
    for operand in ['"dog food"', "(dog OR cat)", "dog*"]:
        positive = _build(operand, primary_field="display_name")
        assert _complement_of(_build(f"NOT {operand}", primary_field="display_name")) == positive


def test_raw_affiliation_door_complement():
    f = "authorships.raw_affiliation_strings"
    positive = _build("harvard", primary_field=f)
    assert _complement_of(_build("NOT harvard", primary_field=f)) == positive


def test_citation_boost_wraps_the_complement():
    d = SearchOpenAlex(search_terms="NOT dog", primary_field="display_name").build_query().to_dict()
    assert set(d) == {"function_score"}
    _complement_of(d["function_score"]["query"])


def test_semantic_search_is_not_complemented(monkeypatch):
    # The detector would fire on the text, but build_query routes semantic
    # search to its own (kNN) path before the complement branch: no bool wrapper.
    from elasticsearch_dsl import Q
    monkeypatch.setattr(SearchOpenAlex, "semantic_query", lambda self: Q("match_all"))
    s = SearchOpenAlex(search_terms="NOT dog", is_semantic_query=True)
    assert whole_query_negation_operand(s.search_terms) == "dog"
    assert "must_not" not in str(s.build_query(skip_citation_boost=True).to_dict())


# ---- multi-operand leading NOT: Lucene semantics via query_string --------

def test_multi_operand_leading_not_goes_to_query_string():
    d = _build("NOT dog cat", primary_field="display_name")
    assert "query_string" in str(d)
    assert d["query_string"]["query"] == "NOT dog cat"


def test_lowercase_not_stays_plain_words():
    # `not dog` is two words on the analyzed branch (stopword drop is the
    # analyzer's business, not a negation).
    d = _build("not dog", primary_field="display_name")
    assert "must_not" not in str(d) and "query_string" not in str(d)


def test_not_between_terms_unchanged():
    d = _build("dog NOT cat", primary_field="display_name")
    assert d["query_string"]["query"] == "dog NOT cat"
