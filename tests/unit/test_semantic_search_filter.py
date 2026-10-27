"""oxjob #1886: `filter=semantic.search:...` answers a JSON 400 that names search.semantic.

The filter form built a kNN on the old in-index vectors through an Elasticsearch ML model that no longer exists, so
every call was an HTML 500 (~140 calls in the week to 26 Oct, several from AI agents). Semantic search is the
`search.semantic` parameter, which runs on the vector index and takes filters alongside it.
"""
import pytest

from core.exceptions import APIQueryParamsError
from core.fields import SearchField


def test_semantic_search_filter_is_a_400_that_names_the_parameter():
    field = SearchField(param="semantic.search", custom_es_field="vector_embedding")
    field.value = "coral reef bleaching"
    with pytest.raises(APIQueryParamsError) as err:
        field.build_query()
    assert "search.semantic" in str(err.value.message if hasattr(err.value, "message") else err.value)


def test_other_search_filters_still_build():
    field = SearchField(param="title.search", custom_es_field="display_name")
    field.value = "coral reef bleaching"
    assert field.build_query() is not None
