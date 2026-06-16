"""Functional tests for query EXECUTION at the root (oxjob #372 Phase 3).

oql/oqo embed the entity type, so they execute at the root — next to
`/works?filter=…` — rather than under `/query/...` (the pure translation
resource):

    GET  /?oql=<oql>
    GET  /?oqo=<urlencoded_json>
    POST /  body {"oqo": {...}} | {"oql": "..."}

A bare `GET /` (no oql/oqo) still returns the "Don't panic" descriptor. The old
`POST /query` execute form is removed.

`execute_search` is patched so these run without a live ES (same pattern as
test_oqo_query_endpoint.py::TestPostExecutes).
"""

import json
import urllib.parse
from unittest.mock import patch


# ---------------------------------------------------------------------------
# Stubs: build the Search without running ES
# ---------------------------------------------------------------------------


class _StubHits:
    total = type("T", (), {"value": 7})()


class _StubResponse:
    took = 3
    hits = _StubHits()

    def __iter__(self):
        return iter([])


def _fake_execute(captured):
    def _inner(s, params):
        captured.append(s.to_dict())
        return _StubResponse()

    return _inner


WORKS_OQO = {
    "get_rows": "works",
    "filter_rows": [{"column_id": "type", "value": "article"}],
}


def _valid_oql(client):
    """Round-trip an oxurl through translation to get a parser-valid OQL string."""
    base = client.get("/query/oxurl/works?filter=type:article").get_json()
    return base["oql"]


# ---------------------------------------------------------------------------
# Bare root still returns the descriptor
# ---------------------------------------------------------------------------


class TestBareRoot:
    def test_bare_get_returns_descriptor(self, client):
        res = client.get("/")
        assert res.status_code == 200
        body = res.get_json()
        assert body["msg"] == "Don't panic"
        assert "documentation_url" in body


# ---------------------------------------------------------------------------
# Execution: all four forms reach execute_search and echo the OQO
# ---------------------------------------------------------------------------


class TestRootExecutes:
    def test_get_oqo_executes(self, client):
        captured = []
        encoded = urllib.parse.quote(json.dumps(WORKS_OQO), safe="")
        with patch(
            "query_translation.execution.execute_search",
            side_effect=_fake_execute(captured),
        ):
            res = client.get(f"/?oqo={encoded}")
        assert res.status_code == 200, res.get_json()
        assert len(captured) == 1
        # Canonical query echo moved from top-level `oqo` (#372) to meta.x_query (#373).
        assert res.get_json()["meta"]["x_query"]["oqo"]["get_rows"] == "works"

    def test_post_oqo_executes(self, client):
        captured = []
        with patch(
            "query_translation.execution.execute_search",
            side_effect=_fake_execute(captured),
        ):
            res = client.post(
                "/",
                data=json.dumps({"oqo": WORKS_OQO}),
                content_type="application/json",
            )
        assert res.status_code == 200, res.get_json()
        assert len(captured) == 1
        # Canonical query echo moved from top-level `oqo` (#372) to meta.x_query (#373).
        assert res.get_json()["meta"]["x_query"]["oqo"]["get_rows"] == "works"

    def test_get_oql_executes(self, client):
        oql = _valid_oql(client)
        captured = []
        with patch(
            "query_translation.execution.execute_search",
            side_effect=_fake_execute(captured),
        ):
            res = client.get("/?oql=" + urllib.parse.quote(oql, safe=""))
        assert res.status_code == 200, res.get_json()
        assert len(captured) == 1
        # Canonical query echo moved from top-level `oqo` (#372) to meta.x_query (#373).
        assert res.get_json()["meta"]["x_query"]["oqo"]["get_rows"] == "works"

    def test_post_oql_executes(self, client):
        oql = _valid_oql(client)
        captured = []
        with patch(
            "query_translation.execution.execute_search",
            side_effect=_fake_execute(captured),
        ):
            res = client.post(
                "/",
                data=json.dumps({"oql": oql}),
                content_type="application/json",
            )
        assert res.status_code == 200, res.get_json()
        assert len(captured) == 1


# ---------------------------------------------------------------------------
# Error hygiene: malformed input is 400 (never 500)
# ---------------------------------------------------------------------------


def _assert_400(res):
    assert res.status_code == 400, res.get_json()
    body = res.get_json()
    assert body["validation"]["valid"] is False
    assert len(body["validation"]["errors"]) >= 1


class TestRootErrors:
    def test_post_non_object_body_returns_400(self, client):
        res = client.post(
            "/",
            data=json.dumps([1, 2, 3]),
            content_type="application/json",
        )
        _assert_400(res)

    def test_post_without_oqo_or_oql_returns_400(self, client):
        res = client.post(
            "/",
            data=json.dumps({"foo": "bar"}),
            content_type="application/json",
        )
        _assert_400(res)

    def test_get_invalid_oqo_json_returns_400(self, client):
        res = client.get("/?oqo=not_valid_json")
        _assert_400(res)

    def test_get_invalid_oql_returns_400(self, client):
        res = client.get("/?oql=" + urllib.parse.quote("this is not oql !!", safe=""))
        _assert_400(res)

    def test_get_empty_oql_returns_400(self, client):
        res = client.get("/?oql=")
        _assert_400(res)


# ---------------------------------------------------------------------------
# The old execute form is gone
# ---------------------------------------------------------------------------


class TestOldExecuteFormRemoved:
    def test_post_query_no_longer_executes(self, client):
        # Execution moved to the root; `POST /query` is removed. `/query` is now
        # GET-only (translation descriptor) → POST yields 405 (or 404 if the
        # route is fully absent). Either way it must NOT execute (no 200).
        res = client.post(
            "/query",
            data=json.dumps({"get_rows": "works"}),
            content_type="application/json",
        )
        assert res.status_code in (404, 405), res.status_code


# ---------------------------------------------------------------------------
# Semantic (vector) search routes through the OQO execution path (oxjob #363).
#
# A `*.search.semantic` leaf is a two-phase kNN over the dedicated vector index,
# NOT an ordinary `Q` match. Case 30 fixed only the OQO→URL render direction; an
# OQO *executed* directly (`/?oqo=`) used to silently run a plain single-pass
# match. These assert it now routes to `vector_semantic_search` (prod path) /
# `add_semantic_search` (single-index fallback) instead — and that the
# non-semantic filters reach the vector pre-filter via the same renderer the
# URL path uses, so the two can't diverge.
# ---------------------------------------------------------------------------


def _semantic_result():
    """A minimal vector_semantic_search-shaped result (no live ES)."""
    return {
        "meta": {
            "count": 0,
            "db_response_time_ms": 1,
            "page": 1,
            "per_page": 25,
            "groups_count": None,
        },
        "group_by": [],
        "results": [],
    }


def _semantic_oqo(extra_filters=None):
    oqo = {
        "get_rows": "works",
        "filter_rows": [
            {
                "column_id": "abstract.search.semantic",
                "value": "graph neural networks",
                "operator": "has",
            }
        ],
    }
    if extra_filters:
        oqo["filter_rows"].extend(extra_filters)
    return oqo


class TestSemanticOqoExecution:
    def test_semantic_oqo_routes_to_vector_search(self, client):
        """A semantic OQO hits vector_semantic_search, NOT the plain Q path."""
        captured = {}

        def _fake_vss(params, index_name, connection):
            captured["params"] = params
            captured["index_name"] = index_name
            return _semantic_result()

        encoded = urllib.parse.quote(json.dumps(_semantic_oqo()), safe="")
        with patch("settings.USE_VECTOR_INDEX", True), patch(
            "query_translation.execution.vector_semantic_search",
            side_effect=_fake_vss,
        ), patch(
            "query_translation.execution.execute_search",
            side_effect=AssertionError("plain ES path must not run for semantic"),
        ):
            res = client.get(f"/?oqo={encoded}")

        assert res.status_code == 200, res.get_json()
        # The query text reaches the vector search as params["search"].
        assert captured["params"]["search"] == "graph neural networks"
        assert captured["params"]["search_type"] == "semantic"
        assert captured["index_name"].lower().startswith("works")
        # Canonical echo still attached.
        assert res.get_json()["meta"]["x_query"]["oqo"]["get_rows"] == "works"

    def test_semantic_oqo_passes_filters_to_vector_prefilter(self, client):
        """Non-semantic filters reach the vector pre-filter in legacy URL-dict
        form (same shape build_vector_filter consumes), plus the is_xpac default."""
        captured = {}

        def _fake_vss(params, index_name, connection):
            captured["params"] = params
            return _semantic_result()

        oqo = _semantic_oqo(
            extra_filters=[
                {"column_id": "publication_year", "value": 2020, "operator": ">"},
                {"column_id": "type", "value": "article", "operator": "is"},
            ]
        )
        encoded = urllib.parse.quote(json.dumps(oqo), safe="")
        with patch("settings.USE_VECTOR_INDEX", True), patch(
            "query_translation.execution.vector_semantic_search",
            side_effect=_fake_vss,
        ):
            res = client.get(f"/?oqo={encoded}")

        assert res.status_code == 200, res.get_json()
        filters = captured["params"]["filters"]
        assert {"publication_year": ">2020"} in filters
        assert {"type": "article"} in filters
        # works-walden default applied (vector_semantic_search strips it itself).
        assert {"is_xpac": "false"} in filters

    def test_semantic_oqo_respects_include_xpac(self, client):
        """include_xpac=true suppresses the is_xpac:false default."""
        captured = {}

        def _fake_vss(params, index_name, connection):
            captured["params"] = params
            return _semantic_result()

        encoded = urllib.parse.quote(json.dumps(_semantic_oqo()), safe="")
        with patch("settings.USE_VECTOR_INDEX", True), patch(
            "query_translation.execution.vector_semantic_search",
            side_effect=_fake_vss,
        ):
            res = client.get(f"/?oqo={encoded}&include_xpac=true")

        assert res.status_code == 200, res.get_json()
        # Pure semantic + no default → no filters at all.
        assert captured["params"]["filters"] is None

    def test_negated_semantic_oqo_is_400_not_silent_match(self, client):
        """A negated semantic clause can't ride the single vector param → 400
        (rather than silently degrading to a normal match)."""
        oqo = {
            "get_rows": "works",
            "filter_rows": [
                {
                    "column_id": "abstract.search.semantic",
                    "value": "graph neural networks",
                    "operator": "has",
                    "is_negated": True,
                }
            ],
        }
        encoded = urllib.parse.quote(json.dumps(oqo), safe="")
        with patch("settings.USE_VECTOR_INDEX", True), patch(
            "query_translation.execution.vector_semantic_search",
            side_effect=AssertionError("must not run for an invalid semantic shape"),
        ):
            res = client.get(f"/?oqo={encoded}")
        assert res.status_code == 400, res.get_json()

    def test_semantic_oqo_fallback_to_single_index_when_vector_off(self, client):
        """USE_VECTOR_INDEX off → route to add_semantic_search (single-index kNN),
        still NOT the plain non-semantic Q path."""
        calls = {"add_semantic": 0}

        def _fake_add_semantic(params, fields_dict, s):
            calls["add_semantic"] += 1
            return s

        captured = []
        with patch("settings.USE_VECTOR_INDEX", False), patch(
            "query_translation.execution.add_semantic_search",
            side_effect=_fake_add_semantic,
        ), patch(
            "query_translation.execution.execute_search",
            side_effect=_fake_execute(captured),
        ):
            encoded = urllib.parse.quote(json.dumps(_semantic_oqo()), safe="")
            res = client.get(f"/?oqo={encoded}")

        assert res.status_code == 200, res.get_json()
        assert calls["add_semantic"] == 1
        assert len(captured) == 1  # went through execute_search exactly once
