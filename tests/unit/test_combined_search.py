"""Unit tests for combined search parameter validation and extraction."""

import pytest
from werkzeug.datastructures import MultiDict
from werkzeug.test import EnvironBuilder


class FakeRequest:
    """Minimal request-like object for testing."""

    def __init__(self, args_dict):
        # args_dict can be a list of (key, value) tuples to support duplicates
        if isinstance(args_dict, list):
            self.args = MultiDict(args_dict)
        else:
            self.args = MultiDict(args_dict)
        self.url = "http://test/works?" + "&".join(
            f"{k}={v}" for k, v in self.args.items(multi=True)
        )


# ---- Validation Tests ----

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

# Mock settings module before importing validate
sys.modules['settings'] = type(sys)('settings')
sys.modules['settings'].ES_URL_WALDEN = 'http://localhost:9200'
sys.modules['settings'].DEBUG = False
sys.modules['settings'].USE_VECTOR_INDEX = False
sys.modules['settings'].DO_NOT_GROUP_BY = []
sys.modules['settings'].BOOLEAN_TEXT_FIELDS = []
sys.modules['settings'].EXTERNAL_ID_FIELDS = []

from core.validate import validate_search_param, _parse_search_param_name
from core.exceptions import APIQueryParamsError


class TestParseSearchParamName:
    def test_bare_search(self):
        assert _parse_search_param_name("search") == ("bare", "default")

    def test_bare_exact(self):
        assert _parse_search_param_name("search.exact") == ("bare", "exact")

    def test_semantic(self):
        assert _parse_search_param_name("search.semantic") == ("semantic", "semantic")

    def test_title(self):
        assert _parse_search_param_name("search.title") == ("title", "default")

    def test_title_exact(self):
        assert _parse_search_param_name("search.title.exact") == ("title", "exact")

    def test_title_and_abstract(self):
        assert _parse_search_param_name("search.title_and_abstract") == (
            "title_and_abstract", "default"
        )

    def test_title_and_abstract_exact(self):
        assert _parse_search_param_name("search.title_and_abstract.exact") == (
            "title_and_abstract", "exact"
        )


class TestValidateSearchParam:
    def test_single_search_allowed(self):
        req = FakeRequest({"search": "hello"})
        validate_search_param(req)  # Should not raise

    def test_single_scoped_allowed(self):
        req = FakeRequest({"search.title": "hello"})
        validate_search_param(req)

    def test_multiple_different_scoped_allowed(self):
        req = FakeRequest({
            "search.title": "amphibian",
            "search.title_and_abstract": "frog",
        })
        validate_search_param(req)  # Should not raise

    def test_bare_plus_scoped_allowed(self):
        req = FakeRequest({
            "search": "climate",
            "search.title": "ocean",
        })
        validate_search_param(req)  # Should not raise

    def test_semantic_alone_allowed(self):
        req = FakeRequest({"search.semantic": "machine learning"})
        validate_search_param(req)

    def test_semantic_combined_rejected(self):
        req = FakeRequest({
            "search.semantic": "machine learning",
            "search.title": "neural",
        })
        with pytest.raises(APIQueryParamsError, match="search.semantic cannot be combined"):
            validate_search_param(req)

    def test_same_scope_different_type_rejected(self):
        req = FakeRequest({
            "search.title": "hello",
            "search.title.exact": "world",
        })
        with pytest.raises(APIQueryParamsError, match="Cannot use both stemmed and exact"):
            validate_search_param(req)

    def test_bare_and_bare_exact_rejected(self):
        req = FakeRequest({
            "search": "hello",
            "search.exact": "world",
        })
        with pytest.raises(APIQueryParamsError, match="Cannot use both stemmed and exact"):
            validate_search_param(req)

    def test_bang_operator_rejected(self):
        req = FakeRequest({"search.title": "!zoo"})
        with pytest.raises(APIQueryParamsError, match="does not support the ! operator"):
            validate_search_param(req)

    def test_pipe_operator_rejected(self):
        req = FakeRequest({"search.title": "dna|rna"})
        with pytest.raises(APIQueryParamsError, match="does not support the \\| operator"):
            validate_search_param(req)

    def test_bang_operator_with_multiple_searches(self):
        req = FakeRequest({
            "search.title": "hello",
            "search.title_and_abstract": "!zoo",
        })
        with pytest.raises(APIQueryParamsError, match="does not support the ! operator"):
            validate_search_param(req)


# ---- Parameter Extraction Tests ----

from core.params import _extract_all_search_params


class TestExtractAllSearchParams:
    def test_no_search_params(self):
        req = FakeRequest({"filter": "type:article"})
        assert _extract_all_search_params(req) == []

    def test_single_bare_search(self):
        req = FakeRequest({"search": "hello"})
        result = _extract_all_search_params(req)
        assert len(result) == 1
        assert result[0] == {
            "search": "hello",
            "search_type": "default",
            "search_scope": None,
        }

    def test_single_scoped_search(self):
        req = FakeRequest({"search.title": "hello"})
        result = _extract_all_search_params(req)
        assert len(result) == 1
        assert result[0] == {
            "search": "hello",
            "search_type": "default",
            "search_scope": "title",
        }

    def test_multiple_searches(self):
        req = FakeRequest({
            "search.title": "amphibian",
            "search.title_and_abstract": "frog",
        })
        result = _extract_all_search_params(req)
        assert len(result) == 2
        scopes = {r["search_scope"] for r in result}
        assert scopes == {"title", "title_and_abstract"}

    def test_bare_plus_scoped(self):
        req = FakeRequest({
            "search": "climate",
            "search.title": "ocean",
        })
        result = _extract_all_search_params(req)
        assert len(result) == 2
        searches = {r["search"] for r in result}
        assert searches == {"climate", "ocean"}

    def test_semantic_search(self):
        req = FakeRequest({"search.semantic": "machine learning"})
        result = _extract_all_search_params(req)
        assert len(result) == 1
        assert result[0]["search_type"] == "semantic"
        assert result[0]["search_scope"] is None


# ---- Preference Tests ----

from core.preference import combine_preferences


class TestCombinePreferences:
    def test_single(self):
        result = combine_preferences(["hello"])
        assert result == "hello"

    def test_multiple_sorted(self):
        result = combine_preferences(["beta", "alpha"])
        assert result == "alpha|beta"

    def test_underscore_prefix(self):
        result = combine_preferences(["_test"])
        assert result == "underscoretest"
