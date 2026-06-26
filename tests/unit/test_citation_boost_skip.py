"""Unit tests for skipping the citation boost when _score is unused (oxjob #520).

The boost (a function_score wrapper) only affects results when ES ranks hits by
relevance _score. When the response can't read _score for ordering — aggregation
(group_by), sample-as-filter, or an explicit non-relevance sort — wrapping the
query in function_score is wasted scoring work and should be omitted.
"""

import pytest
from elasticsearch_dsl import Search

from core.shared_view import add_search_query, citation_boost_needed


def _params(**overrides):
    """Minimal params dict with the keys add_search_query / citation_boost_needed read."""
    base = {
        "searches": [],
        "search": None,
        "search_scope": None,
        "search_type": None,
        "sample": None,
        "group_by": None,
        "sort": None,
    }
    base.update(overrides)
    return base


def _has_function_score(params, index_name="works-v33"):
    s = add_search_query(params, index_name, Search())
    return "function_score" in str(s.to_dict())


# ---- citation_boost_needed: pure decision logic ----

class TestCitationBoostNeeded:
    def test_default_search_no_sort(self):
        assert citation_boost_needed(_params(search="covid")) is True

    def test_relevance_score_sort(self):
        assert citation_boost_needed(
            _params(search="covid", sort={"relevance_score": "desc"})
        ) is True

    def test_field_sort_skips(self):
        assert citation_boost_needed(
            _params(search="covid", sort={"publication_date": "desc"})
        ) is False

    def test_group_by_skips(self):
        assert citation_boost_needed(
            _params(search="covid", group_by="type")
        ) is False

    def test_sample_skips(self):
        assert citation_boost_needed(
            _params(search="covid", sample=10)
        ) is False

    def test_group_by_wins_over_relevance_sort(self):
        # size=0 means no hits regardless of sort key → still skip.
        assert citation_boost_needed(
            _params(search="covid", group_by="type", sort={"relevance_score": "desc"})
        ) is False


# ---- add_search_query: single search ----

class TestSingleSearchBoost:
    def test_default_search_has_boost(self, client):
        assert _has_function_score(_params(search="covid")) is True

    def test_relevance_sort_has_boost(self, client):
        assert _has_function_score(
            _params(search="covid", sort={"relevance_score": "desc"})
        ) is True

    def test_field_sort_no_boost(self, client):
        assert _has_function_score(
            _params(search="covid", sort={"publication_date": "desc"})
        ) is False

    def test_group_by_no_boost(self, client):
        assert _has_function_score(
            _params(search="covid", group_by="type")
        ) is False

    def test_sample_no_boost(self, client):
        assert _has_function_score(
            _params(search="covid", sample=10)
        ) is False


# ---- add_search_query: multiple searches ----

class TestMultiSearchBoost:
    def _multi(self, **overrides):
        searches = [
            {"search": "amphibian", "search_scope": None, "search_type": "default"},
            {"search": "frog", "search_scope": None, "search_type": "default"},
        ]
        return _params(searches=searches, **overrides)

    def test_default_multi_has_boost(self, client):
        assert _has_function_score(self._multi()) is True

    def test_field_sort_multi_no_boost(self, client):
        assert _has_function_score(
            self._multi(sort={"publication_date": "desc"})
        ) is False

    def test_group_by_multi_no_boost(self, client):
        assert _has_function_score(self._multi(group_by="type")) is False

    def test_relevance_sort_multi_has_boost(self, client):
        assert _has_function_score(
            self._multi(sort={"relevance_score": "desc"})
        ) is True
