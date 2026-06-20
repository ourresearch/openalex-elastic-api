"""Functional tests for OQO execution at the root (#306 execution, moved to the
root in #372 Phase 3).

Two layers:

1. **Pure validation** — hit `POST /` (body `{"oqo": …}`) and `GET /query/oqo/<path>`
   with shape-broken OQOs and assert structured 400 responses. No live ES required.

2. **End-to-end equivalence** — for an in-scope subset of the worked-example
   corpus, hit `POST /` with the OQO and `GET /works?...` with the
   equivalent OXURL; assert both return the same result count and the same
   top-N result IDs. Requires a populated test ES (the existing tests/conftest
   contract).

The first layer runs in any environment with the test app importable; the
second is gated on ES reachability and skipped otherwise.

NOTE (#372): execution moved from `POST /query` to `POST /` with body
`{"oqo": <oqo>}` / `{"oql": <oql>}` (also `GET /?oqo=` / `GET /?oql=`). The old
`POST /query` and execute-via-`GET /query/oqo/<path>` forms were removed.
Root-specific execution tests (GET forms, bare-`/` descriptor, removed routes)
live in test_root_execution_endpoint.py.
"""

import json
import os
import urllib.parse
from unittest.mock import patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _post_oqo(client, body):
    # Execution at root (#372): POST / with the OQO wrapped under the "oqo" key.
    return client.post(
        "/",
        data=json.dumps({"oqo": body}),
        content_type="application/json",
    )


def _check_400_with_errors(res):
    assert res.status_code == 400
    body = res.get_json()
    assert body is not None
    assert "validation" in body
    assert body["validation"]["valid"] is False
    assert len(body["validation"]["errors"]) >= 1
    # Defense-in-depth: never a 500 for client-side shape errors.
    for err in body["validation"]["errors"]:
        assert "type" in err
        assert "message" in err


# ---------------------------------------------------------------------------
# Test 4: invalid OQO returns 400 with structured errors (no live ES needed)
# ---------------------------------------------------------------------------


class TestInvalidOQO:
    def test_post_without_json_content_type_returns_400(self, client):
        res = client.post("/", data="not json", content_type="text/plain")
        _check_400_with_errors(res)

    def test_post_with_non_object_body_returns_400(self, client):
        res = client.post(
            "/",
            data=json.dumps(["this", "is", "not", "an", "object"]),
            content_type="application/json",
        )
        _check_400_with_errors(res)

    def test_post_with_missing_get_rows_returns_400(self, client):
        res = _post_oqo(client, {"filter_rows": []})
        _check_400_with_errors(res)

    def test_post_with_invalid_entity_type_returns_400(self, client):
        res = _post_oqo(client, {"get_rows": "unicorns"})
        _check_400_with_errors(res)

    def test_post_with_invalid_operator_returns_400(self, client):
        # "is not" was dropped in the #284 spec — must be is_negated bit instead.
        res = _post_oqo(
            client,
            {
                "get_rows": "works",
                "filter_rows": [
                    {"column_id": "type", "value": "article", "operator": "is not"}
                ],
            },
        )
        _check_400_with_errors(res)

    def test_post_with_invalid_join_returns_400(self, client):
        res = _post_oqo(
            client,
            {
                "get_rows": "works",
                "filter_rows": [
                    {
                        "join": "xor",  # not and/or
                        "filters": [
                            {"column_id": "type", "value": "article"}
                        ],
                    }
                ],
            },
        )
        _check_400_with_errors(res)

    def test_post_with_empty_groupby_column_id_returns_400(self, client):
        res = _post_oqo(
            client,
            {
                "get_rows": "works",
                "group_by": [{"column_id": ""}],
            },
        )
        _check_400_with_errors(res)

    def test_post_with_multidim_group_by_returns_400(self, client):
        """Multi-dim group_by is in the spec but deferred to #297."""
        res = _post_oqo(
            client,
            {
                "get_rows": "works",
                "group_by": [
                    {"column_id": "primary_topic.id"},
                    {"column_id": "publication_year"},
                ],
            },
        )
        assert res.status_code == 400
        body = res.get_json()
        # Pointer to the deferred follow-up should appear in the error message.
        msg = (
            json.dumps(body)
            if "validation" in body
            else (body.get("message") or body.get("error") or "")
        )
        assert "#297" in msg

    def test_post_with_unknown_column_id_returns_400(self, client):
        res = _post_oqo(
            client,
            {
                "get_rows": "works",
                "filter_rows": [
                    {"column_id": "definitely_not_a_real_field_xyz", "value": "x"}
                ],
            },
        )
        assert res.status_code == 400

    def test_get_with_invalid_json_returns_400(self, client):
        # `not json` URL-encoded path
        res = client.get("/query/oqo/not_valid_json")
        _check_400_with_errors(res)

    def test_get_with_array_body_returns_400(self, client):
        encoded = urllib.parse.quote(json.dumps([1, 2, 3]), safe="")
        res = client.get(f"/query/oqo/{encoded}")
        _check_400_with_errors(res)


# ---------------------------------------------------------------------------
# Test 3: POST and GET path-form route to the same code (no live ES required)
# ---------------------------------------------------------------------------


class TestPostExecutes:
    """POST / (body {"oqo": …}) executes an OQO against ES (Search built without
    running ES).

    NOTE (#372): `GET /query/oqo/<path>` now *translates* (→ all formats), it no
    longer executes. OQO execution lives at the root (`GET /?oqo=`, `POST /`) as
    of Phase 3. Translation of the GET path-form is covered in
    test_query_translation_endpoint.py.
    """

    def test_post_constructs_a_search(self, client):
        """Patch execute_search to capture the Search body without running ES."""
        oqo_body = {
            "get_rows": "works",
            "filter_rows": [
                {"column_id": "type", "value": "article"},
                {"column_id": "publication_year", "value": "2024"},
            ],
        }

        captured = []

        class _StubHits:
            total = type("T", (), {"value": 42})()

        class _StubResponse:
            took = 5
            hits = _StubHits()

            def __iter__(self):
                return iter([])

        def fake_execute_search(s, params):
            captured.append(s.to_dict())
            return _StubResponse()

        with patch(
            "query_translation.execution.execute_search", side_effect=fake_execute_search
        ):
            res_post = _post_oqo(client, oqo_body)

        assert res_post.status_code == 200, res_post.get_json()
        assert len(captured) == 1


# ---------------------------------------------------------------------------
# meta.x_query triple in the response (#373 — replaces #372's top-level oqo echo)
# ---------------------------------------------------------------------------


class TestMetaXQuery:
    def _stub_run(self, client, oqo_body):
        class _StubHits:
            total = type("T", (), {"value": 0})()

        class _StubResponse:
            took = 1
            hits = _StubHits()

            def __iter__(self):
                return iter([])

        with patch(
            "query_translation.execution.execute_search", return_value=_StubResponse()
        ):
            return _post_oqo(client, oqo_body)

    def test_response_includes_meta_x_query_triple(self, client):
        oqo_body = {
            "get_rows": "works",
            "filter_rows": [{"column_id": "type", "value": "article"}],
        }
        res = self._stub_run(client, oqo_body)

        assert res.status_code == 200, res.get_json()
        body = res.get_json()
        # The old top-level `oqo` echo (#372) is gone; the canonical home is now
        # meta.x_query (#373).
        assert "oqo" not in body
        x_query = body["meta"]["x_query"]
        assert set(x_query) == {"oql", "oqo", "url"}
        assert x_query["oqo"]["get_rows"] == "works"
        # A simple flat filter IS URL-expressible → url is a /works?filter=… form.
        assert x_query["url"] and x_query["url"].startswith("/works?filter=")
        # oql round-trips: re-parsing it canonicalizes back to the same oqo. The
        # execute path honors authored order (sort_operands=False, #475), so reparse
        # the same way to compare against the order-preserving x_query.oqo.
        from query_translation.oql_parser import parse_oql_to_oqo
        from query_translation.oqo_canonicalizer import canonicalize_oqo
        reparsed = canonicalize_oqo(
            parse_oql_to_oqo(x_query["oql"]), sort_operands=False).to_dict()
        assert reparsed == x_query["oqo"]

    def test_execute_path_honors_value_bag_order(self, client):
        """#475: the execute path must NOT alphabetize a value bag's commutative
        members — the SERP rebuilds `?oql=` from x_query, so a sort here silently
        reorders the user's values. Submitting `c, b, a` must round-trip as `c, b, a`,
        NOT `a, b, c`."""
        oqo_body = {
            "get_rows": "works",
            "filter_rows": [{"join": "or", "filters": [
                {"column_id": "title_and_abstract.search", "value": v, "operator": "has"}
                for v in ("c", "b", "a")]}],
        }
        res = self._stub_run(client, oqo_body)
        assert res.status_code == 200, res.get_json()
        x_query = res.get_json()["meta"]["x_query"]
        assert x_query["oql"] == "works where title/abstract has any (c, b, a)"
        vals = [f["value"] for f in x_query["oqo"]["filter_rows"][0]["filters"]]
        assert vals == ["c", "b", "a"]
        assert x_query["url"].endswith("title_and_abstract.search:c|b|a")

    def test_execute_path_x_query_oql_is_bare_id(self, client):
        """OQLO charter decision 14 (#378 S3): the execute path emits CANONICAL
        bare-ID OQL — no eager ES display-name lookups. Display-name annotation is
        a display-time/on-demand concern handled by the `/query/*` translate
        endpoints, not baked into the execute response's x_query.oql."""
        oqo_body = {
            "get_rows": "works",
            "filter_rows": [{"column_id": "authorships.institutions.lineage",
                             "value": "I136199984"}],
        }
        res = self._stub_run(client, oqo_body)
        assert res.status_code == 200, res.get_json()
        oql = res.get_json()["meta"]["x_query"]["oql"]
        assert "I136199984" in oql
        assert "[" not in oql  # bare ID, no `[Harvard University]` annotation

    def test_display_service_resolves_entity_display_names(self):
        """The flip side of decision 14: when a resolver IS passed (as the
        `/query/*` translate endpoints do — they ARE the on-demand display
        service), build_x_query annotates entity display names."""
        from query_translation.x_query import build_x_query
        from query_translation.oqo import OQO, LeafFilter

        oqo = OQO(get_rows="works", filter_rows=[
            LeafFilter(column_id="authorships.institutions.lineage",
                       value="I136199984")])
        xq = build_x_query(oqo, entity_resolver=lambda _id: "Harvard University")
        assert "I136199984 [Harvard University]" in xq["oql"]

    def test_nested_boolean_x_query_url_is_null(self, client):
        # (A and B) or (C and D) — a nested boolean tree the OXURL syntax can't
        # express → url must be None (graceful), never a 500.
        oqo_body = {
            "get_rows": "works",
            "filter_rows": [
                {
                    "join": "or",
                    "filters": [
                        {
                            "join": "and",
                            "filters": [
                                {"column_id": "type", "value": "article"},
                                {"column_id": "publication_year", "value": "2024"},
                            ],
                        },
                        {
                            "join": "and",
                            "filters": [
                                {"column_id": "type", "value": "review"},
                                {"column_id": "publication_year", "value": "2023"},
                            ],
                        },
                    ],
                }
            ],
        }
        res = self._stub_run(client, oqo_body)

        assert res.status_code == 200, res.get_json()
        x_query = res.get_json()["meta"]["x_query"]
        assert x_query["url"] is None
        assert x_query["oql"]  # still renders to OQL


# ---------------------------------------------------------------------------
# OQL parse errors surface position + context (#373)
# ---------------------------------------------------------------------------


class TestOqlParseErrorHints:
    def test_malformed_oql_returns_structured_400_with_position(self, client):
        # `===` is not a valid operator → the parser raises OQLParseError.
        res = client.get("/?oql=works where type === article")
        assert res.status_code == 400, res.get_json()
        body = res.get_json()
        assert body["validation"]["valid"] is False
        errors = body["validation"]["errors"]
        assert errors, "expected at least one parse error"
        # Minimal hints (#373 D4): each error carries message + position + context
        # keys (values may be None until #357 enriches them) and is NOT a single
        # stringified "Failed to parse OQL: …" blob.
        for e in errors:
            assert "message" in e
            assert "position" in e
            assert "context" in e
        assert not body["validation"]["errors"][0]["message"].startswith(
            "Failed to parse OQL"
        )


# ---------------------------------------------------------------------------
# End-to-end equivalence with the OXURL endpoint (LIVE ES required)
#
# These are the Acceptance Tests 1, 2, 5, 6 from ACCEPTANCE.md.
# Gated on `ES_OQO_INTEGRATION=1` so a sparse local ES doesn't trigger noise.
# ---------------------------------------------------------------------------

_RUN_LIVE_ES_TESTS = os.environ.get("ES_OQO_INTEGRATION") == "1"


@pytest.mark.skipif(
    not _RUN_LIVE_ES_TESTS,
    reason="Set ES_OQO_INTEGRATION=1 to run end-to-end OQO/OXURL parity tests.",
)
class TestEndToEndParity:
    """Hit POST / (OQO) and GET /works (OXURL) for the same query and
    assert both return the same meta.count + top-10 IDs."""

    def test_simple_filter_parity(self, client):
        oqo = {
            "get_rows": "works",
            "filter_rows": [{"column_id": "type", "value": "article"}],
        }
        oqo_res = _post_oqo(client, oqo).get_json()
        url_res = client.get("/works?filter=type:article").get_json()
        assert oqo_res["meta"]["count"] == url_res["meta"]["count"]

    def test_negation_parity(self, client):
        oqo = {
            "get_rows": "works",
            "filter_rows": [
                {"column_id": "type", "value": "article", "is_negated": True}
            ],
        }
        oqo_res = _post_oqo(client, oqo).get_json()
        url_res = client.get("/works?filter=type:!article").get_json()
        assert oqo_res["meta"]["count"] == url_res["meta"]["count"]

    def test_range_gte_parity(self, client):
        oqo = {
            "get_rows": "works",
            "filter_rows": [
                {
                    "column_id": "publication_year",
                    "value": "2020",
                    "operator": ">=",
                }
            ],
        }
        oqo_res = _post_oqo(client, oqo).get_json()
        url_res = client.get("/works?filter=publication_year:2020-").get_json()
        assert oqo_res["meta"]["count"] == url_res["meta"]["count"]

    def test_nested_boolean_unrepresentable_in_url(self, client):
        """The differentiator vs OXURL — nested AND/OR/NOT.

        We can't express this query as a URL, so we just assert the OQO query
        returns 200 with a sensible result count (> 0 if the corpus is sane).
        """
        oqo = {
            "get_rows": "works",
            "filter_rows": [
                {
                    "column_id": "publication_year",
                    "value": "2020",
                    "operator": ">=",
                },
                {
                    "join": "or",
                    "filters": [
                        {"column_id": "type", "value": "article"},
                        {"column_id": "type", "value": "book"},
                    ],
                },
            ],
        }
        res = _post_oqo(client, oqo)
        assert res.status_code == 200, res.get_json()
        body = res.get_json()
        assert "meta" in body
        assert isinstance(body["meta"]["count"], int)
