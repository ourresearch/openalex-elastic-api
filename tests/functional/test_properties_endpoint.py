"""Functional tests for the /properties surface (#331 Phase 2 — ACCEPTANCE Test 3).

Exercises the live Flask routes via the test client (no ES needed — the catalog
builds at boot from the live Field objects):
  - GET /properties (full) + ?entity= slice
  - GET /properties/<entity> (== the ?entity= slice, byte-for-byte)
  - GET /registry, /registry/<entity> as DEPRECATED aliases (identical body +
    `Deprecation` header)
  - unknown entity → 404 invalid_entity
  - server-internal keys (alias/custom_es_field) are NOT in the public payload.

Needs the test app (tests/conftest `client` fixture) — run WITHOUT --noconftest.
"""


def _get_json(client, path):
    resp = client.get(path)
    return resp, resp.get_json()


def test_properties_full_payload(client):
    resp, body = _get_json(client, "/properties")
    assert resp.status_code == 200
    assert body["meta"]["version"]  # present, non-empty
    assert len(body["meta"]["fingerprint"]) == 64
    assert body["meta"]["entity_count"] == len(body["properties"])
    assert body["meta"]["property_count"] == sum(
        len(c) for c in body["properties"].values()
    )
    assert "works" in body["properties"]


def test_properties_entity_query_param_slices(client):
    resp, body = _get_json(client, "/properties?entity=works")
    assert resp.status_code == 200
    assert set(body["properties"].keys()) == {"works"}
    assert body["meta"]["entity"] == "works"
    # meta still describes the FULL catalog identity
    full = client.get("/properties").get_json()
    assert body["meta"]["fingerprint"] == full["meta"]["fingerprint"]
    assert body["meta"]["entity_count"] == full["meta"]["entity_count"]


def test_query_param_slice_equals_nested_route(client):
    a = client.get("/properties?entity=works").get_json()
    b = client.get("/properties/works").get_json()
    assert a == b


def test_unknown_entity_is_404(client):
    for path in ("/properties?entity=bogus", "/properties/bogus"):
        resp = client.get(path)
        assert resp.status_code == 404, path
        body = resp.get_json()
        assert body["validation"]["errors"][0]["type"] == "invalid_entity"


def test_registry_alias_is_deprecated_but_identical(client):
    new = client.get("/properties")
    old = client.get("/registry")
    assert old.status_code == 200
    assert old.get_json() == new.get_json()  # identical body
    assert old.headers.get("Deprecation") == "true"
    assert "/properties" in old.headers.get("Link", "")
    # the new route is NOT marked deprecated
    assert new.headers.get("Deprecation") is None


def test_registry_entity_alias_is_deprecated_but_identical(client):
    new = client.get("/properties/works")
    old = client.get("/registry/works")
    assert old.status_code == 200
    assert old.get_json() == new.get_json()
    assert old.headers.get("Deprecation") == "true"


def test_registry_unknown_entity_alias_is_404(client):
    resp = client.get("/registry/bogus")
    assert resp.status_code == 404
    assert resp.get_json()["validation"]["errors"][0]["type"] == "invalid_entity"


def test_public_payload_omits_server_internal_keys(client):
    body = client.get("/properties?entity=works").get_json()
    sample = next(iter(body["properties"]["works"].values()))
    assert set(sample.keys()) == {"name", "type", "operators", "actions", "entity_type"}
    assert "custom_es_field" not in sample
    assert "alias" not in sample
