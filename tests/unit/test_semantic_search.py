"""Unit tests for core.semantic_search query embedding (oxjob #1275).

Guards the Qwen3 cutover: the query side must carry the instruction prefix and name the
multilingual endpoint. The corpus was embedded WITHOUT the prefix, so a regression here
(prefix dropped, or applied to documents) silently degrades every semantic search.
"""
import json
from unittest.mock import patch, MagicMock

import pytest

from core import semantic_search
from core.exceptions import APIQueryParamsError


def _mock_post(embedding=None):
    """A stand-in for requests.post returning one embedding."""
    response = MagicMock()
    response.raise_for_status.return_value = None
    response.json.return_value = {
        "data": [{"embedding": embedding or [0.0] * semantic_search.EMBEDDING_DIMENSION}]
    }
    return response


def test_model_is_qwen3_multilingual():
    assert semantic_search.EMBEDDING_MODEL == "databricks-qwen3-embedding-0-6b"
    assert semantic_search.EMBEDDING_DIMENSION == 1024


def test_query_instruction_shape():
    """Must match the prefix the benchmark used, including the newline before 'Query: '."""
    assert semantic_search.QUERY_INSTRUCTION == (
        "Instruct: Given a web search query, retrieve relevant passages that answer the query\n"
        "Query: "
    )


@patch.object(semantic_search, "_get_access_token", return_value="tok")
@patch.object(semantic_search.settings, "DATABRICKS_HOST", "example.cloud.databricks.com")
@patch.object(semantic_search.http_requests, "post")
def test_embed_query_sends_prefix_and_model(mock_post, _token):
    mock_post.return_value = _mock_post()

    vector = semantic_search.embed_query("protein folding")

    assert len(vector) == semantic_search.EMBEDDING_DIMENSION
    payload = mock_post.call_args.kwargs["json"]
    assert payload["model"] == "databricks-qwen3-embedding-0-6b"
    assert payload["input"].startswith(semantic_search.QUERY_INSTRUCTION)
    assert payload["input"].endswith("protein folding")


@patch.object(semantic_search, "_get_access_token", return_value="tok")
@patch.object(semantic_search.settings, "DATABRICKS_HOST", "example.cloud.databricks.com")
@patch.object(semantic_search.http_requests, "post")
def test_embed_query_truncates_before_prefixing(mock_post, _token):
    """The 2000-char cap applies to the user's text, not to the instruction."""
    mock_post.return_value = _mock_post()

    semantic_search.embed_query("x" * 5000)

    payload = mock_post.call_args.kwargs["json"]
    assert payload["input"] == semantic_search.QUERY_INSTRUCTION + "x" * 2000


@pytest.mark.parametrize("bad", ["", "   ", None])
def test_embed_query_rejects_empty(bad):
    with pytest.raises(APIQueryParamsError):
        semantic_search.embed_query(bad)
