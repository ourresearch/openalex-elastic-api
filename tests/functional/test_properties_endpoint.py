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
    # display_name + aliases are public as of v1.3.0 (#381); category as of v1.13.0
    # (#441); alias/custom_es_field remain server-internal and must never leak.
    assert set(sample.keys()) == {
        "name", "type", "operators", "actions", "entity_type",
        "display_name", "aliases", "category",
    }
    assert "custom_es_field" not in sample
    assert "alias" not in sample


# --- #318 select unification (ACCEPTANCE Test 5, select half) ----------------
# The catalog carries filter-columns ∪ selectable result-fields, discriminated by
# `actions`. NOTE the two source namespaces (PLAN's examples are nominal):
#   - select-only field is `abstract_inverted_index` (NOT a bare `abstract`),
#   - `open_access` is select-only (the FILTER column is `open_access.is_oa`),
#   - `publication_year` is the clean both-filterable-and-selectable case.

def test_select_only_field_is_a_property_with_select_action(client):
    works = client.get("/properties/works").get_json()["properties"]["works"]
    for name in ("abstract_inverted_index", "open_access"):
        assert name in works, f"{name} should appear as a (select-only) property"
        prop = works[name]
        assert prop["actions"] == ["select"]
        # select-only ⇒ not filterable: no value type, no operators.
        assert prop["type"] is None
        assert prop["operators"] == []


# --- #441 category (organizational grouping) ---------------------------------
# A nullable, best-effort grouping mirroring the GUI facetConfigs categories. No
# query-behavior effect, no enforcement gate — so we assert a few representative
# assignments AND that null is a valid, present outcome (the long tail).

def test_category_known_assignments(client):
    works = client.get("/properties/works").get_json()["properties"]["works"]
    expected = {
        "cited_by_count": "citation",       # citation metric
        "doi": "ids",                       # identifier
        "open_access.oa_status": "open access",
        "publication_year": "dates",        # the #441 registry addition
        "publication_date": "dates",
        "authorships.author.id": "author",
        "primary_topic.id": "aboutness",
    }
    for name, category in expected.items():
        assert works[name]["category"] == category, f"{name} -> {works[name]['category']!r}"


def test_category_is_present_and_nullable(client):
    works = client.get("/properties/works").get_json()["properties"]["works"]
    # Every property carries the key (part of the public payload as of v1.13.0)…
    assert all("category" in p for p in works.values())
    # …and null is a legitimate, intentional value for the uncategorized long tail
    # (select-only `abstract_inverted_index` has no facet peer and no clear bucket).
    assert works["abstract_inverted_index"]["category"] is None


def test_filterable_and_selectable_field_unions_actions(client):
    works = client.get("/properties/works").get_json()["properties"]["works"]
    py = works["publication_year"]
    assert "filter" in py["actions"]
    assert "select" in py["actions"]


def test_filter_only_column_has_no_select_action(client):
    # `open_access.is_oa` is filter-only; the selectable object is the parent
    # `open_access`. The two must not be conflated.
    works = client.get("/properties/works").get_json()["properties"]["works"]
    assert "select" not in works["open_access.is_oa"]["actions"]
