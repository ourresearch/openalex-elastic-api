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


def _spy_merge(merged):
    """Wrap _merge_view_params to record the merged INTERNAL OQO (the execution
    struct that carries the folded view params). #661: the public x_query echo
    sheds sort_by/select/paging, so "the sibling was honored" is observed here
    (and/or on the captured ES query), never on the echo."""
    import query_translation.execution as _execution_mod

    real = _execution_mod._merge_view_params

    def _inner(oqo, request, body_params=None):
        out = real(oqo, request, body_params)
        merged.append(out)
        return out

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


class TestStrictPostBody:
    """The POST body may contain `oql`/`oqo` plus the sibling view params
    (sort/select/page/per_page/cursor — #661 query/view split). Anything else
    is a hard 400 (#631): unknown keys used to be silently ignored, the classic
    OQL-adjacent footgun."""

    def test_unknown_top_level_key_is_400(self, client):
        captured = []
        oql = _valid_oql(client)
        with patch(
            "query_translation.execution.execute_search",
            side_effect=_fake_execute(captured),
        ):
            res = client.post(
                "/",
                # `sample` belongs INSIDE the OQO, not as a sibling — still 400.
                data=json.dumps({"oql": oql, "sample": 5}),
                content_type="application/json",
            )
        _assert_400(res)
        # Never reached execution (the whole point — no silent drop).
        assert captured == []
        err = res.get_json()["validation"]["errors"][0]
        assert err["type"] == "invalid_body"
        assert "sample" in err["message"]

    def test_unknown_key_alongside_oqo_is_400(self, client):
        res = client.post(
            "/",
            data=json.dumps({"oqo": WORKS_OQO, "frobnicate": True}),
            content_type="application/json",
        )
        _assert_400(res)
        assert "frobnicate" in res.get_json()["validation"]["errors"][0]["message"]

    def test_both_oql_and_oqo_is_400(self, client):
        res = client.post(
            "/",
            data=json.dumps({"oql": "works", "oqo": WORKS_OQO}),
            content_type="application/json",
        )
        _assert_400(res)
        assert "both" in res.get_json()["validation"]["errors"][0]["message"]

    def test_clean_single_key_body_still_executes(self, client):
        """Regression guard: a well-formed single-key body is unaffected."""
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


class TestIntegerSeedCoerced:
    """An integer `seed` in an OQO used to 500 (preference hashing calls
    `.encode()` on it). It's now coerced to its string form at ingestion,
    matching the OQL text path's canonical `"42"` (#631)."""

    def test_integer_seed_does_not_500_and_canonicalizes_to_string(self, client):
        captured = []
        oqo = {
            "get_rows": "works",
            "filter_rows": [{"column_id": "publication_year", "value": 2020}],
            "sample": 5,
            "seed": 42,
        }
        with patch(
            "query_translation.execution.execute_search",
            side_effect=_fake_execute(captured),
        ):
            res = client.post(
                "/",
                data=json.dumps({"oqo": oqo}),
                content_type="application/json",
            )
        assert res.status_code == 200, res.get_json()
        # Canonical echo carries the string form (parity with `sample 5 seed 42`).
        assert res.get_json()["meta"]["x_query"]["oqo"]["seed"] == "42"

    def test_string_seed_unchanged(self, client):
        captured = []
        oqo = {
            "get_rows": "works",
            "filter_rows": [{"column_id": "publication_year", "value": 2020}],
            "sample": 5,
            "seed": "42",
        }
        with patch(
            "query_translation.execution.execute_search",
            side_effect=_fake_execute(captured),
        ):
            res = client.post(
                "/",
                data=json.dumps({"oqo": oqo}),
                content_type="application/json",
            )
        assert res.status_code == 200, res.get_json()
        assert res.get_json()["meta"]["x_query"]["oqo"]["seed"] == "42"


# ---------------------------------------------------------------------------
# The old execute form is gone
# ---------------------------------------------------------------------------


class TestOldExecuteFormRemoved:
    def test_post_query_no_longer_executes(self, client):
        # Execution moved to the root and never came back. `POST /query` was later
        # re-introduced as a TRANSLATE route (oxjob #428 — the body-based sibling of
        # GET /query/{oql|oqo}/<value>, for queries too long for a URL), so it must
        # still NOT execute: a bare execute-style OQO body (no {"oqo": ...} wrapper)
        # is rejected (400, "needs oql/oqo/oxurl"), and the response is never an
        # execution envelope (no `results`).
        res = client.post(
            "/query",
            data=json.dumps({"get_rows": "works"}),
            content_type="application/json",
        )
        assert res.status_code == 400, res.status_code
        assert "results" not in (res.get_json() or {})

    def test_post_query_translates_but_never_executes(self, client):
        # A properly-wrapped translate POST returns the translation payload
        # (oql/oqo/validation/oql_render_v2) — and crucially NO execution envelope.
        res = client.post("/query", json={"oqo": {"get_rows": "works"}})
        assert res.status_code == 200, res.get_json()
        body = res.get_json()
        assert "results" not in body and "meta" not in body
        assert "oql" in body and "oql_render_v2" in body


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


# ---------------------------------------------------------------------------
# Sibling view params (#661 query/view split; classic query-string fold #631).
#
# Sorting + field selection + pagination are VIEW concerns — not part of the
# public OQO. They travel as siblings of the query (query-string params on
# either verb, or top-level body keys on POST) and are folded into the OQO's
# internal view fields before validation, so they run + validate + echo like
# the old OQO-native sort_by/select. Precedence: body sibling > query-string
# sibling > (transition) a value still embedded in the OQO dict.
# ---------------------------------------------------------------------------


class TestClassicSortSelectHonored:
    def _oql(self, client):
        return _valid_oql(client)

    def test_query_string_sort_is_honored_with_oql(self, client):
        """?sort= next to ?oql= reaches ES sort AND the x_query echo (not ignored)."""
        captured = []
        oql = self._oql(client)
        with patch(
            "query_translation.execution.execute_search",
            side_effect=_fake_execute(captured),
        ):
            res = client.get(
                "/?oql=" + urllib.parse.quote(oql, safe="") + "&sort=cited_by_count:asc"
            )
        assert res.status_code == 200, res.get_json()
        # #661: the echo sheds view keys, so honoring is observed on the ES
        # query. ES renders an ascending sort as the bare field name (asc is
        # its default); desc becomes {field:{order}}.
        assert "sort_by" not in res.get_json()["meta"]["x_query"]["oqo"]
        es_sort = captured[0].get("sort")
        assert es_sort and es_sort[0] == "cited_by_count"

    def test_query_string_select_is_honored_with_oql(self, client):
        """?select= next to ?oql= is folded into oqo.select (drives projection)."""
        captured = []
        merged = []
        oql = self._oql(client)
        with patch(
            "query_translation.execution.execute_search",
            side_effect=_fake_execute(captured),
        ), patch(
            "query_translation.execution._merge_view_params",
            side_effect=_spy_merge(merged),
        ):
            res = client.get(
                "/?oql="
                + urllib.parse.quote(oql, safe="")
                + "&select=id,display_name"
            )
        assert res.status_code == 200, res.get_json()
        # Folded into the internal execution struct; the echo sheds it (#661).
        assert merged[0].select == ["id", "display_name"]
        assert "select" not in res.get_json()["meta"]["x_query"]["oqo"]

    def test_multi_key_sort_preserves_priority(self, client):
        """Comma-separated sort keeps primary→secondary order (tiebreaker priority)."""
        captured = []
        merged = []
        oql = self._oql(client)
        with patch(
            "query_translation.execution.execute_search",
            side_effect=_fake_execute(captured),
        ), patch(
            "query_translation.execution._merge_view_params",
            side_effect=_spy_merge(merged),
        ):
            res = client.get(
                "/?oql="
                + urllib.parse.quote(oql, safe="")
                + "&sort=publication_year:asc,cited_by_count:desc"
            )
        assert res.status_code == 200, res.get_json()
        assert [x.to_dict() for x in merged[0].sort_by] == [
            {"column_id": "publication_year", "direction": "asc"},
            {"column_id": "cited_by_count", "direction": "desc"},
        ]

    def test_directionless_sort_defaults_asc(self, client):
        """A bare `sort=col` defaults to asc, matching the legacy URL path."""
        captured = []
        merged = []
        oql = self._oql(client)
        with patch(
            "query_translation.execution.execute_search",
            side_effect=_fake_execute(captured),
        ), patch(
            "query_translation.execution._merge_view_params",
            side_effect=_spy_merge(merged),
        ):
            res = client.get(
                "/?oql=" + urllib.parse.quote(oql, safe="") + "&sort=cited_by_count"
            )
        assert res.status_code == 200, res.get_json()
        assert [x.to_dict() for x in merged[0].sort_by] == [
            {"column_id": "cited_by_count", "direction": "asc"}
        ]

    def test_query_string_sort_wins_over_embedded_oqo_sort_by(self, client):
        """The sibling is the documented surface (#661): ?sort= overrides a
        sort_by still embedded in the OQO dict (the pre-#661 transition shape).
        Pre-#661 the OQO won; the flip is deliberate."""
        captured = []
        oqo = {
            "get_rows": "works",
            "filter_rows": [{"column_id": "type", "value": "article"}],
            "sort_by": [{"column_id": "publication_year", "direction": "desc"}],
        }
        encoded = urllib.parse.quote(json.dumps(oqo), safe="")
        merged = []
        with patch(
            "query_translation.execution.execute_search",
            side_effect=_fake_execute(captured),
        ), patch(
            "query_translation.execution._merge_view_params",
            side_effect=_spy_merge(merged),
        ):
            res = client.get(f"/?oqo={encoded}&sort=cited_by_count:asc")
        assert res.status_code == 200, res.get_json()
        assert [x.to_dict() for x in merged[0].sort_by] == [
            {"column_id": "cited_by_count", "direction": "asc"}
        ]

    def test_query_string_select_wins_over_embedded_oqo_select(self, client):
        """?select= overrides a select still embedded in the OQO dict (#661)."""
        captured = []
        oqo = {
            "get_rows": "works",
            "filter_rows": [{"column_id": "type", "value": "article"}],
            "select": ["id"],
        }
        encoded = urllib.parse.quote(json.dumps(oqo), safe="")
        merged = []
        with patch(
            "query_translation.execution.execute_search",
            side_effect=_fake_execute(captured),
        ), patch(
            "query_translation.execution._merge_view_params",
            side_effect=_spy_merge(merged),
        ):
            res = client.get(f"/?oqo={encoded}&select=id,display_name,cited_by_count")
        assert res.status_code == 200, res.get_json()
        assert merged[0].select == [
            "id",
            "display_name",
            "cited_by_count",
        ]

    def test_embedded_oqo_view_keys_still_accepted_without_siblings(self, client):
        """Transition back-compat (#661): an OQO still carrying embedded
        sort_by/select/per_page (today's GUI shape) with NO siblings executes
        exactly as before — no 400, values honored."""
        captured = []
        oqo = {
            "get_rows": "works",
            "filter_rows": [{"column_id": "type", "value": "article"}],
            "sort_by": [{"column_id": "publication_year", "direction": "desc"}],
            "select": ["id", "display_name"],
            "per_page": 7,
        }
        encoded = urllib.parse.quote(json.dumps(oqo), safe="")
        merged = []
        with patch(
            "query_translation.execution.execute_search",
            side_effect=_fake_execute(captured),
        ), patch(
            "query_translation.execution._merge_view_params",
            side_effect=_spy_merge(merged),
        ):
            res = client.get(f"/?oqo={encoded}")
        assert res.status_code == 200, res.get_json()
        assert [x.to_dict() for x in merged[0].sort_by] == [
            {"column_id": "publication_year", "direction": "desc"}
        ]
        assert merged[0].select == ["id", "display_name"]
        assert merged[0].per_page == 7
        # …but the echo conforms to the public spec: no view keys (#661).
        echo = res.get_json()["meta"]["x_query"]["oqo"]
        for view_key in ("sort_by", "select", "page", "per_page", "cursor"):
            assert view_key not in echo


class TestBodyViewParams:
    """POST-body sibling view params (#661): {"oqo": …, "sort": …, "select": …,
    "page": …, "per_page": …, "cursor": …} — same classic syntax as the
    query-string form, plus a JSON-list convenience for select."""

    def test_body_sort_select_per_page_are_honored(self, client):
        captured = []
        merged = []
        with patch(
            "query_translation.execution.execute_search",
            side_effect=_fake_execute(captured),
        ), patch(
            "query_translation.execution._merge_view_params",
            side_effect=_spy_merge(merged),
        ):
            res = client.post(
                "/",
                data=json.dumps({
                    "oqo": WORKS_OQO,
                    "sort": "cited_by_count:desc",
                    "select": "id,display_name",
                    "per_page": 7,
                }),
                content_type="application/json",
            )
        assert res.status_code == 200, res.get_json()
        assert [x.to_dict() for x in merged[0].sort_by] == [
            {"column_id": "cited_by_count", "direction": "desc"}
        ]
        assert merged[0].select == ["id", "display_name"]
        # per_page actually shaped the ES query (size = per_page).
        assert captured[0].get("size") == 7
        # The echo conforms to the public spec: no view keys (#661).
        echo = res.get_json()["meta"]["x_query"]["oqo"]
        for view_key in ("sort_by", "select", "page", "per_page", "cursor"):
            assert view_key not in echo

    def test_body_select_accepts_json_list(self, client):
        captured = []
        merged = []
        with patch(
            "query_translation.execution.execute_search",
            side_effect=_fake_execute(captured),
        ), patch(
            "query_translation.execution._merge_view_params",
            side_effect=_spy_merge(merged),
        ):
            res = client.post(
                "/",
                data=json.dumps({"oqo": WORKS_OQO, "select": ["id", "doi"]}),
                content_type="application/json",
            )
        assert res.status_code == 200, res.get_json()
        assert merged[0].select == ["id", "doi"]

    def test_body_sibling_wins_over_embedded_oqo_value(self, client):
        """Acceptance #3 (#661): sibling sort beats an embedded sort_by."""
        captured = []
        merged = []
        oqo = dict(WORKS_OQO)
        oqo["sort_by"] = [{"column_id": "display_name", "direction": "asc"}]
        with patch(
            "query_translation.execution.execute_search",
            side_effect=_fake_execute(captured),
        ), patch(
            "query_translation.execution._merge_view_params",
            side_effect=_spy_merge(merged),
        ):
            res = client.post(
                "/",
                data=json.dumps({"oqo": oqo, "sort": "cited_by_count:desc"}),
                content_type="application/json",
            )
        assert res.status_code == 200, res.get_json()
        assert [x.to_dict() for x in merged[0].sort_by] == [
            {"column_id": "cited_by_count", "direction": "desc"}
        ]

    def test_body_sibling_wins_over_query_string_sibling(self, client):
        captured = []
        merged = []
        with patch(
            "query_translation.execution.execute_search",
            side_effect=_fake_execute(captured),
        ), patch(
            "query_translation.execution._merge_view_params",
            side_effect=_spy_merge(merged),
        ):
            res = client.post(
                "/?sort=display_name:asc",
                data=json.dumps({"oqo": WORKS_OQO, "sort": "cited_by_count:desc"}),
                content_type="application/json",
            )
        assert res.status_code == 200, res.get_json()
        assert [x.to_dict() for x in merged[0].sort_by] == [
            {"column_id": "cited_by_count", "direction": "desc"}
        ]

    def test_body_sort_wrong_type_is_400(self, client):
        res = client.post(
            "/",
            data=json.dumps({"oqo": WORKS_OQO, "sort": ["cited_by_count"]}),
            content_type="application/json",
        )
        _assert_400(res)

    def test_body_per_page_wrong_type_is_400(self, client):
        res = client.post(
            "/",
            data=json.dumps({"oqo": WORKS_OQO, "per_page": "seven"}),
            content_type="application/json",
        )
        _assert_400(res)

    def test_body_unknown_sort_column_is_structured_400(self, client):
        res = client.post(
            "/",
            data=json.dumps({"oqo": WORKS_OQO, "sort": "not_a_real_field:asc"}),
            content_type="application/json",
        )
        _assert_400(res)
        assert res.get_json()["validation"]["valid"] is False

    def test_body_view_params_work_with_oql_too(self, client):
        captured = []
        merged = []
        oql = _valid_oql(client)
        with patch(
            "query_translation.execution.execute_search",
            side_effect=_fake_execute(captured),
        ), patch(
            "query_translation.execution._merge_view_params",
            side_effect=_spy_merge(merged),
        ):
            res = client.post(
                "/",
                data=json.dumps({"oql": oql, "sort": "cited_by_count:desc"}),
                content_type="application/json",
            )
        assert res.status_code == 200, res.get_json()
        assert [x.to_dict() for x in merged[0].sort_by] == [
            {"column_id": "cited_by_count", "direction": "desc"}
        ]

    def test_query_string_sort_select_honored_on_post_oql(self, client):
        """The fold works on the POST body form too (args are method-agnostic)."""
        captured = []
        merged = []
        oql = _valid_oql(client)
        with patch(
            "query_translation.execution.execute_search",
            side_effect=_fake_execute(captured),
        ), patch(
            "query_translation.execution._merge_view_params",
            side_effect=_spy_merge(merged),
        ):
            res = client.post(
                "/?sort=cited_by_count:asc&select=id",
                data=json.dumps({"oql": oql}),
                content_type="application/json",
            )
        assert res.status_code == 200, res.get_json()
        assert [x.to_dict() for x in merged[0].sort_by] == [
            {"column_id": "cited_by_count", "direction": "asc"}
        ]
        assert merged[0].select == ["id"]

    def test_malformed_sort_is_400_not_500(self, client):
        """A malformed ?sort= surfaces as a clean 400, never a raw 500."""
        oql = _valid_oql(client)
        res = client.get(
            "/?oql=" + urllib.parse.quote(oql, safe="") + "&sort=" +
            urllib.parse.quote("a:b:c", safe="")
        )
        assert res.status_code == 400, res.get_json()


class TestXQueryEchoShedsViewState:
    """#661 slice-2 companion: meta.x_query never hands the client view state.
    The echoed oqo conforms to the public spec (v1.4 — no sort_by/select/page/
    per_page/cursor) and the url form sheds sort=/select= on every execute path."""

    def test_get_oql_with_all_siblings_echo_is_pure(self, client):
        captured = []
        oql = _valid_oql(client)
        with patch(
            "query_translation.execution.execute_search",
            side_effect=_fake_execute(captured),
        ):
            res = client.get(
                "/?oql=" + urllib.parse.quote(oql, safe="")
                + "&sort=cited_by_count:desc&select=id,doi&page=2&per_page=5"
            )
        assert res.status_code == 200, res.get_json()
        x_query = res.get_json()["meta"]["x_query"]
        for view_key in ("sort_by", "select", "page", "per_page", "cursor"):
            assert view_key not in x_query["oqo"]
        assert "sort=" not in (x_query["url"] or "")
        assert "select=" not in (x_query["url"] or "")

    def test_post_embedded_view_keys_echo_is_pure(self, client):
        captured = []
        oqo = dict(WORKS_OQO)
        oqo["sort_by"] = [{"column_id": "cited_by_count", "direction": "desc"}]
        oqo["select"] = ["id", "doi"]
        oqo["per_page"] = 5
        with patch(
            "query_translation.execution.execute_search",
            side_effect=_fake_execute(captured),
        ):
            res = client.post(
                "/",
                data=json.dumps({"oqo": oqo}),
                content_type="application/json",
            )
        assert res.status_code == 200, res.get_json()
        x_query = res.get_json()["meta"]["x_query"]
        for view_key in ("sort_by", "select", "page", "per_page", "cursor"):
            assert view_key not in x_query["oqo"]
        assert "sort=" not in (x_query["url"] or "")
        assert "select=" not in (x_query["url"] or "")

    def test_unknown_select_column_is_structured_400(self, client):
        """An unknown ?select= column → structured invalid_select_column 400."""
        oql = _valid_oql(client)
        res = client.get(
            "/?oql=" + urllib.parse.quote(oql, safe="") + "&select=not_a_real_field"
        )
        assert res.status_code == 400, res.get_json()
        body = res.get_json()
        assert body["validation"]["valid"] is False
        assert any(
            e.get("type") == "invalid_select_column"
            for e in body["validation"]["errors"]
        )

    def test_unknown_sort_column_is_structured_400(self, client):
        """An unknown ?sort= column → structured sort validation 400."""
        oql = _valid_oql(client)
        res = client.get(
            "/?oql=" + urllib.parse.quote(oql, safe="") + "&sort=not_a_real_field:asc"
        )
        assert res.status_code == 400, res.get_json()
        assert res.get_json()["validation"]["valid"] is False
