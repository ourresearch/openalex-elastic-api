"""Functional tests for the /query *translation* resource (#372).

Translation routes take a query in one representation and return ALL of them:
  GET /query/oxurl/:query
  GET /query/oql/:query
  GET /query/oqo/:query
→ {oxurl, oql, oql_render, oqo, validation}

These need no live ES — parsing/validation/rendering are pure (the URL parser
reads the static field registry in core.properties).
"""

import json
import urllib.parse

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _leaf_count(oqo):
    """Count leaf filters (nodes carrying column_id) — mirrors the GUI's
    oqoLeafCount, which is what #369 uses for the min-complexity metric."""
    def count(node):
        if node is None:
            return 0
        if isinstance(node, list):
            return sum(count(n) for n in node)
        if isinstance(node, dict):
            if "filter_rows" in node:
                return count(node["filter_rows"])
            if "filters" in node:
                return count(node["filters"])
            if "column_id" in node:
                return 1
        return 0
    return count(oqo.get("filter_rows"))


def _all_formats_present(body):
    for k in ("oxurl", "oql", "oql_render", "oqo", "validation"):
        assert k in body, f"missing {k} in {body}"
    assert body["validation"]["valid"] is True


# ---------------------------------------------------------------------------
# Translation across formats
# ---------------------------------------------------------------------------


class TestTranslateOxurl:
    def test_two_filter_oxurl_translates_to_all_formats(self, client):
        res = client.get("/query/oxurl/works?filter=publication_year:2020,type:article")
        assert res.status_code == 200, res.get_json()
        body = res.get_json()
        _all_formats_present(body)
        assert body["oqo"]["get_rows"] == "works"
        assert _leaf_count(body["oqo"]) == 2

    def test_or_options_count_as_distinct_leaves(self, client):
        # type:article|book|dataset → BranchFilter(or) with 3 leaves (#369 metric)
        res = client.get("/query/oxurl/works?filter=type:article|book|dataset")
        assert res.status_code == 200, res.get_json()
        assert _leaf_count(res.get_json()["oqo"]) == 3

    def test_raw_and_urlencoded_inputs_are_equivalent(self, client):
        raw = client.get("/query/oxurl/works?filter=type:article")
        encoded_seg = urllib.parse.quote("works?filter=type:article", safe="")
        enc = client.get(f"/query/oxurl/{encoded_seg}")
        assert raw.status_code == 200 and enc.status_code == 200
        assert raw.get_json()["oqo"] == enc.get_json()["oqo"]

    def test_scoped_search_param_folds_into_filter(self, client):
        # search.title_and_abstract=foo should become a title_and_abstract.search leaf
        res = client.get("/query/oxurl/works?search.title_and_abstract=cancer")
        assert res.status_code == 200, res.get_json()
        oqo = res.get_json()["oqo"]
        assert _leaf_count(oqo) >= 1

    def test_invalid_entity_returns_400(self, client):
        res = client.get("/query/oxurl/unicorns?filter=type:article")
        assert res.status_code == 400
        assert res.get_json()["validation"]["valid"] is False


class TestTranslateRoundTrips:
    """oxurl → oql → oqo should all describe the same canonical query."""

    def test_oql_from_oxurl_round_trips_to_same_oqo(self, client):
        base = client.get(
            "/query/oxurl/works?filter=publication_year:2020,type:article"
        ).get_json()
        oql = base["oql"]
        viaoql = client.get(
            "/query/oql/" + urllib.parse.quote(oql, safe="")
        )
        assert viaoql.status_code == 200, viaoql.get_json()
        assert viaoql.get_json()["oqo"] == base["oqo"]

    def test_oqo_json_round_trips(self, client):
        base = client.get("/query/oxurl/works?filter=type:article").get_json()
        oqo_json = json.dumps(base["oqo"])
        viaoqo = client.get("/query/oqo/" + urllib.parse.quote(oqo_json, safe=""))
        assert viaoqo.status_code == 200, viaoqo.get_json()
        assert viaoqo.get_json()["oqo"] == base["oqo"]


class TestTranslateMetaParams:
    """Request query params (?mailto=…) are meta, never part of the value (#428).

    The oxurl route folds the querystring back into the value (an oxurl's own
    params arrive that way); oql/oqo must NOT — folding made the parser read
    `?mailto=ui%40openalex.org` as OQL tokens.
    """

    def test_oql_ignores_request_query_params(self, client):
        res = client.get(
            "/query/oql/" + urllib.parse.quote("works where type is article", safe="")
            + "?mailto=ui@openalex.org"
        )
        assert res.status_code == 200, res.get_json()
        assert res.get_json()["validation"]["valid"] is True

    def test_oqo_ignores_request_query_params(self, client):
        oqo_json = json.dumps({"get_rows": "works"})
        res = client.get(
            "/query/oqo/" + urllib.parse.quote(oqo_json, safe="") + "?mailto=ui@openalex.org"
        )
        assert res.status_code == 200, res.get_json()


class TestTranslateErrors:
    def test_malformed_oqo_returns_400_not_500(self, client):
        res = client.get("/query/oqo/" + urllib.parse.quote("{not json", safe=""))
        assert res.status_code == 400
        assert res.get_json()["validation"]["valid"] is False

    def test_malformed_oql_returns_400_not_500(self, client):
        res = client.get("/query/oql/" + urllib.parse.quote("this is not oql !!", safe=""))
        assert res.status_code == 400


class TestQueryDescriptor:
    def test_bare_query_returns_descriptor(self, client):
        res = client.get("/query")
        assert res.status_code == 200
        assert "msg" in res.get_json()


class TestTranslateViaPost:
    """POST /query — the body-based sibling of the GET translate routes, added so
    a query too long for a URL (gunicorn `--limit-request-line 8190`) can still be
    translated/re-rendered by the no-code builder (oxjob #428). Same payload, no ES."""

    # A query whose OQO JSON encodes to well over the 8190-byte URL request-line cap,
    # so it can ONLY be translated via POST (the GET /query/oqo/<json> form 400s at the
    # edge). ~30+ OR-terms across three search clauses, mirroring a real SR query.
    BIG_OQL = (
        'works where title has ( ( ' + ' or '.join(f'"term {i}"' for i in range(60)) + ' ) '
        'and ( ' + ' or '.join(f'"weight {i}"' for i in range(60)) + ' ) ) '
        'and full text has ( ' + ' or '.join(f'"place {i}"' for i in range(40)) + ' )'
    )

    def test_post_oql_matches_get(self, client):
        oql = "works where publication_year is 2020 and type is article"
        p = client.post("/query", json={"oql": oql})
        assert p.status_code == 200, p.get_json()
        g = client.get("/query/oql/" + urllib.parse.quote(oql, safe=""))
        assert p.get_json()["oql_render_v2"] == g.get_json()["oql_render_v2"]
        assert p.get_json()["oql"] == g.get_json()["oql"]

    def test_post_oql_returns_all_formats_incl_v2(self, client):
        res = client.post("/query", json={"oql": "works where title has (a or b or c)"})
        assert res.status_code == 200, res.get_json()
        body = res.get_json()
        _all_formats_present(body)
        assert body["oql_render_v2"] is not None

    def test_post_large_oql_translates(self, client):
        # The whole point: this would exceed the request-line limit as a GET URL.
        import json as _json
        res = client.post("/query", json={"oql": self.BIG_OQL})
        assert res.status_code == 200, res.get_json()
        body = res.get_json()
        assert body["validation"]["valid"] is True
        assert body["oql_render_v2"] is not None
        # confirm the GET form would indeed be over the cap (sanity on the premise)
        assert len(urllib.parse.quote(_json.dumps(body["oqo"]), safe="")) > 8190

    def test_post_oqo_roundtrips(self, client):
        parsed = client.post("/query", json={"oql": "works where is_oa is true"}).get_json()
        res = client.post("/query", json={"oqo": parsed["oqo"]})
        assert res.status_code == 200, res.get_json()
        assert res.get_json()["validation"]["valid"] is True

    def test_post_oxurl(self, client):
        res = client.post("/query", json={"oxurl": "works?filter=type:article"})
        assert res.status_code == 200, res.get_json()
        assert res.get_json()["oqo"]["get_rows"] == "works"

    def test_post_empty_body_400(self, client):
        res = client.post("/query", json={"foo": "bar"})
        assert res.status_code == 400

    def test_post_no_body_400(self, client):
        res = client.post("/query")
        assert res.status_code == 400

    def test_post_malformed_oql_400(self, client):
        res = client.post("/query", json={"oql": "this is not oql !!"})
        assert res.status_code == 400
