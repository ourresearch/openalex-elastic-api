"""Functional test for the /entities listing route (oxjob #405 Phase C).

The route now sources each entity's identity (id / display_name / description)
from THE entity registry (`core.entities`) instead of a second read of the raw
`combined_config` dict — one source of truth. ES counts are stubbed out here so
the test runs without a live cluster (the count path is unchanged by #405).
"""

import works.views


def test_entities_lists_registry_sourced_identity(client, monkeypatch):
    # No live ES — force empty counts so the route falls back to values-length.
    monkeypatch.setattr(works.views, "get_entity_counts", lambda request: {})

    resp = client.get("/entities")
    assert resp.status_code == 200
    body = resp.get_json()
    results = body["results"]

    # The curated display order + inclusion list is preserved (works first, 20 types).
    ids = [e["id"] for e in results]
    assert ids[0] == "works"
    assert body["meta"]["count"] == len(results) == 20

    # Identity fields are present and registry-sourced (match the registry).
    from core.entities import get_entity_type
    for e in results:
        ent = get_entity_type(e["id"])
        assert ent is not None
        assert e["display_name"] == (ent.display_name or e["id"])
        assert e["description"] == (ent.description or "")

    # Closed-vocab entity gets a count from its values length when ES is absent;
    # an open entity (works) gets None.
    by_id = {e["id"]: e for e in results}
    assert by_id["continents"]["count"] == len(get_entity_type("continents").values)
    assert by_id["works"]["count"] is None
