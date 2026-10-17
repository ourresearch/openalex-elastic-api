"""Semantic search answers 503 "busy" when the vector cluster or the query embedding doesn't answer in time (oxjob #1433).

The proxy gives up at 9 s. A vector search slower than its 7 s client timeout, or an embedding slower than 5 s, can't
reach the caller, so the API stops waiting (Elasticsearch cancels the search when the connection closes) and says so
with a 503, which the proxy's semantic ladder counts as overload.
"""
import pytest
import requests

from core import semantic_search, vector_index
from core.exceptions import APIQueryParamsError, SemanticSearchBusyError
from elasticsearch.exceptions import ConnectionTimeout


class _SlowES:
    def search(self, index, body):
        raise ConnectionTimeout("Connection timed out")


def test_a_vector_timeout_is_a_503(monkeypatch):
    monkeypatch.setattr(vector_index.connections, "get_connection", lambda alias: _SlowES())
    monkeypatch.setattr(vector_index, "embed_query", lambda text: [0.1] * 4)
    monkeypatch.setattr(vector_index.settings, "SEMANTIC_TEXT_BOOST", False)
    with pytest.raises(SemanticSearchBusyError) as e:
        vector_index.vector_semantic_search({"search": "coral reefs", "filters": [], "per_page": 25}, "works", "walden")
    assert e.value.code == 503


class _Resp:
    def __init__(self, exc=None):
        self.exc = exc

    def raise_for_status(self):
        if self.exc:
            raise self.exc

    def json(self):
        return {"data": [{"embedding": [0.5, 0.25]}]}


def _embed_with(monkeypatch, post):
    monkeypatch.setattr(semantic_search.settings, "DATABRICKS_HOST", "https://example.cloud.databricks.com")
    monkeypatch.setattr(semantic_search, "_get_access_token", lambda: "token")
    monkeypatch.setattr(semantic_search.http_requests, "post", post)
    return semantic_search.embed_query("coral reefs")


def test_an_embedding_timeout_is_a_503_and_the_wait_is_short(monkeypatch):
    seen = {}

    def post(url, headers, json, timeout):
        seen["timeout"] = timeout
        raise requests.exceptions.ReadTimeout("read timed out")

    with pytest.raises(SemanticSearchBusyError):
        _embed_with(monkeypatch, post)
    assert seen["timeout"] <= 5


def test_other_embedding_failures_keep_their_old_answer(monkeypatch):
    def post(url, headers, json, timeout):
        return _Resp(requests.exceptions.HTTPError("400 Client Error"))

    with pytest.raises(APIQueryParamsError):
        _embed_with(monkeypatch, post)


def test_a_normal_embedding_still_works(monkeypatch):
    assert _embed_with(monkeypatch, lambda url, headers, json, timeout: _Resp()) == [0.5, 0.25]
