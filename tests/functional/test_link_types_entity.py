"""link-types entity wiring (oxjob #2481): the new name of /relationships, the same vocabulary (citation, review and
the four part-of kinds), ids https://openalex.org/link-types/<slug>. Both entities answer until the cutover.
Uses the tests/conftest `client` fixture; ES is never reached (walden builds link-types-v1).

    PYTHONPATH=. venv/bin/python -m pytest tests/functional/test_link_types_entity.py -q
"""
import pytest
from elasticsearch_dsl import AttrDict

import ids.views
from link_types.schemas import LinkTypesSchema
from relationships.schemas import RelationshipsSchema

VALUES = [("citation", "Citation"), ("volume", "Volume"), ("component", "Component"),
          ("data-series", "Data series"), ("part", "Part"), ("review", "Review")]


class _FakeSearch:
    calls = []

    def __init__(self, index=None, using=None):
        self.index = index
        self.queries = []

    def filter(self, q):
        self.queries.append(q.to_dict())
        return self

    def execute(self):
        _FakeSearch.calls.append((self.index, self.queries))
        return []


@pytest.mark.parametrize("path", ["/link-types/Review", "/entities/link-types/review"])
def test_single_record_lookup_uses_the_link_types_path_segment(client, monkeypatch, path):
    # index.split("-")[0] would give "link"; the branch in ids/views keeps "link-types"
    _FakeSearch.calls = []
    monkeypatch.setattr(ids.views, "Search", _FakeSearch)
    r = client.get(path)
    assert r.status_code == 404  # fake ES has no docs
    assert b"No link-types found" in r.data
    index, queries = _FakeSearch.calls[-1]
    assert index == "link-types-v1"
    assert queries == [{"term": {"id.lower": "https://openalex.org/link-types/review"}}]


def test_relationships_single_lookup_is_unchanged(client, monkeypatch):
    _FakeSearch.calls = []
    monkeypatch.setattr(ids.views, "Search", _FakeSearch)
    client.get("/relationships/review")
    assert _FakeSearch.calls[-1] == ("work-relationships-v1",
                                     [{"term": {"id.lower": "https://openalex.org/relationships/review"}}])


def test_config_routes_serve_the_same_six_values_under_each_name(client):
    lt = client.get("/link-types/config")
    rel = client.get("/relationships/config")
    assert lt.status_code == rel.status_code == 200
    assert [(v["id"], v["display_name"]) for v in lt.get_json()["values"]] == [
        (f"link-types/{key}", name) for key, name in VALUES]
    assert [(v["id"], v["display_name"]) for v in rel.get_json()["values"]] == [
        (f"relationships/{key}", name) for key, name in VALUES]


@pytest.mark.parametrize("path", ["/link-types/valid_fields", "/link-types/filters_docstrings"])
def test_helper_routes(client, path):
    r = client.get(path)
    assert r.status_code == 200
    assert "works_count" in r.get_json()


def test_the_record_shape_is_the_relationships_record():
    doc = {"id": "https://openalex.org/link-types/review", "display_name": "Review",
           "description": "The work reviews another work.",
           "standard_terms": [{"vocabulary": "CiTO", "term": "reviews", "url": "http://purl.org/spar/cito/reviews"}],
           "works_count": 7, "works_api_url": None,
           "updated_date": "2026-11-21T00:00:00", "created_date": "2026-11-14", "cited_by_count": 9}
    out = LinkTypesSchema(context={"display_relevance": False}).dump(AttrDict({**doc, "meta": {"score": None}}))
    assert list(out) == ["id", "display_name", "description", "standard_terms", "works_count", "works_api_url",
                         "updated_date", "created_date"]
    assert list(LinkTypesSchema._declared_fields) == list(RelationshipsSchema._declared_fields)


def test_properties_catalog(client):
    props = client.get("/properties").get_json()["properties"]
    assert "link-types" in props and "relationships" in props
    works = props["works"]
    assert works["parent_works.link_type"]["entity_type"] == "link-types"
    assert works["parent_works.link_type"]["display_name"] == "link type to parent work"
    assert "group_by" in works["parent_works.link_type"]["actions"]
    assert works["parent_works.relationship"]["entity_type"] == "relationships"  # unchanged
    assert works["parent_works.relationship"]["display_name"] == "relationship to parent work"
    assert works["reviewed_by_count"]["display_name"] == "reviewed by count"
    assert {"filter", "sort", "column"} <= set(works["reviewed_by_count"]["actions"])
    assert "has_reviews" not in works and "reviewed_by_api_url" not in works


def test_a_works_filter_on_link_type_runs_and_lifts_the_hide_pieces_rule(client):
    from core.default_view import lifts_hiding, request_filter_keys
    assert lifts_hiding(request_filter_keys("parent_works.link_type:component"))
