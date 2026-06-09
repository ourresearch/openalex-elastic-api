"""Functional tests for the /meta catalog tree (oxjob #405 Phase B — ACCEPTANCE
Tests 1 & 2).

Exercises the live Flask routes via the test client (no ES needed — both the
entity registry and the properties catalog build at boot from config + the live
Field objects):

  - GET /meta                                          catalog root
  - GET /meta/entities                                 all 22 entity types
  - GET /meta/entities/<entity>                        one entity (detail)
  - GET /meta/entities/<entity>/properties             == /properties/<entity>
  - GET /meta/entities/<entity>/properties/<property>  one property object
  - unknown entity / property → 404
  - the nested properties route is byte-identical to the published /properties

Needs the test app (tests/conftest `client` fixture) — run WITHOUT --noconftest.
"""

# The 22 browsable entity types in the registry (config/*.yaml). `locations` is a
# properties-only key (reachable via /properties) and intentionally NOT a /meta
# entity — see meta/views.py.
EXPECTED_ENTITY_COUNT = 22


def _json(client, path):
    resp = client.get(path)
    return resp, resp.get_json()


def test_meta_root(client):
    resp, body = _json(client, "/meta")
    assert resp.status_code == 200
    assert body["entities_url"] == "/meta/entities"
    assert body["entity_count"] == EXPECTED_ENTITY_COUNT
    assert body["properties_version"]  # present, non-empty


def test_meta_entities_lists_all_with_required_fields(client):
    resp, body = _json(client, "/meta/entities")
    assert resp.status_code == 200
    assert body["meta"]["count"] == EXPECTED_ENTITY_COUNT
    results = body["results"]
    assert len(results) == EXPECTED_ENTITY_COUNT
    ids = [e["id"] for e in results]
    assert ids == sorted(ids)  # sorted by id
    assert "works" in ids and "authors" in ids
    # Each summary carries id + display name + descr + id format (ACCEPTANCE 1).
    for e in results:
        assert set(e) >= {
            "id", "display_name", "description", "id_format", "properties_url"
        }
        assert e["properties_url"] == f"/meta/entities/{e['id']}/properties"


def test_meta_entity_detail(client):
    resp, body = _json(client, "/meta/entities/works")
    assert resp.status_code == 200
    assert body["id"] == "works"
    assert body["display_name"]
    # works is a native-ID entity: W-prefixed shape, derived native flag True.
    assert body["id_format"]["prefix"] == "W"
    assert body["id_format"]["native"] is True
    # detail-only curated facts
    assert "is_native" in body
    assert "alternate_names" in body
    assert "values" in body  # None for an open entity like works
    assert body["values"] is None


def test_meta_entity_detail_closed_vocab_has_values(client):
    # A closed-vocabulary entity exposes its `values` list.
    body = client.get("/meta/entities/continents").get_json()
    assert isinstance(body["values"], list) and body["values"]
    # continents are Q-shaped (native-*shaped*) yet a closed vocab → authored
    # is_native False while the derived id_format.native is True (#405 nuance).
    assert body["id_format"]["native"] is True
    assert body["is_native"] is False


def test_meta_unknown_entity_404(client):
    for path in ("/meta/entities/bogus", "/meta/entities/bogus/properties"):
        resp = client.get(path)
        assert resp.status_code == 404, path
        assert resp.get_json()["error"]["type"] == "invalid_entity"


def test_meta_properties_equals_published_properties(client):
    """ACCEPTANCE Test 2: the nested route is byte-identical to /properties/<e>
    for every entity — one contract, one source (render_properties)."""
    entity_ids = [e["id"] for e in client.get("/meta/entities").get_json()["results"]]
    for entity in entity_ids:
        nested = client.get(f"/meta/entities/{entity}/properties").get_json()
        published = client.get(f"/properties/{entity}").get_json()
        assert nested == published, entity


def test_meta_single_property_object(client):
    resp, body = _json(
        client, "/meta/entities/works/properties/publication_year"
    )
    assert resp.status_code == 200
    # one property object, embedding the property contract fields (no sub-routes)
    assert body["name"] == "publication_year"
    assert set(body) == {
        "name", "type", "operators", "actions", "entity_type",
        "display_name", "aliases",
    }
    # matches the entry inside the collection route exactly
    coll = client.get("/meta/entities/works/properties").get_json()
    assert body == coll["properties"]["works"]["publication_year"]


def test_meta_unknown_property_404(client):
    resp = client.get("/meta/entities/works/properties/not_a_real_property")
    assert resp.status_code == 404
    assert resp.get_json()["error"]["type"] == "invalid_property"
