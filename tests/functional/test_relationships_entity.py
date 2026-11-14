"""relationships entity wiring (oxjob #2065): the kinds of link between a work and its parent work.
Uses the tests/conftest `client` fixture; ES is never reached (walden builds work-relationships-v1).

    PYTHONPATH=. venv/bin/python -m pytest tests/functional/test_relationships_entity.py -q
"""
import pytest
from elasticsearch_dsl import AttrDict

import ids.views
from relationships.schemas import RelationshipsSchema

# The four records walden syncs (id, display_name, description).
RECORDS = [
    ("volume", "Volume",
     "The work is in a book or proceedings volume: a chapter, entry, front matter or paper of that volume."),
    ("component", "Component",
     "The work is a piece of another work that does not stand alone: a figure, table, file or supplement."),
    ("data-series", "Data series",
     "The work is one record of a data series: datasets published separately that share an instrument and method."),
    ("part", "Part",
     "The work is declared part of another work in some other way: an article in an issue, a dataset in a "
     "collection, a component of a project."),
]


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


@pytest.mark.parametrize("path", ["/relationships/Data-Series", "/work-relationships/data-series",
                                  "/entities/relationships/data-series"])
def test_single_record_lookup_uses_the_relationships_path_segment(client, monkeypatch, path):
    # index.split("-")[0] would give "work"; the branch in ids/views keeps "relationships"
    _FakeSearch.calls = []
    monkeypatch.setattr(ids.views, "Search", _FakeSearch)
    r = client.get(path)
    assert r.status_code == 404  # fake ES has no docs
    assert b"No relationships found" in r.data
    index, queries = _FakeSearch.calls[-1]
    assert index == "work-relationships-v1"
    assert queries == [{"term": {"id.lower": "https://openalex.org/relationships/data-series"}}]


@pytest.mark.parametrize("path", ["/relationships/config", "/work-relationships/config"])
def test_config_route_serves_the_four_values(client, path):
    r = client.get(path)
    assert r.status_code == 200
    assert [(v["id"], v["display_name"]) for v in r.get_json()["values"]] == [
        (f"relationships/{key}", name) for key, name, _ in RECORDS]


@pytest.mark.parametrize("path", ["/relationships/valid_fields", "/work-relationships/valid_fields"])
def test_helper_routes(client, path):
    r = client.get(path)
    assert r.status_code == 200
    assert "works_count" in r.get_json()


def test_the_record_shape():
    for key, name, description in RECORDS:
        doc = {
            "id": f"https://openalex.org/relationships/{key}", "display_name": name, "description": description,
            "works_count": 7, "works_api_url": f"https://api.openalex.org/works?filter=parent_works.relationship:{key}",
            "updated_date": "2026-11-14T00:00:00", "created_date": "2026-11-14",
            "cited_by_count": 9,  # not part of the record
        }
        out = RelationshipsSchema(context={"display_relevance": False}).dump(AttrDict({**doc, "meta": {"score": None}}))
        assert list(out) == ["id", "display_name", "description", "works_count", "works_api_url",
                             "updated_date", "created_date"]
        assert out["description"] == description


def test_properties_catalog(client):
    props = client.get("/properties").get_json()["properties"]
    assert "relationships" in props
    works = props["works"]
    assert works["parent_works.relationship"]["entity_type"] == "relationships"
    assert works["parent_works.relationship"]["display_name"] == "relationship to parent work"
    assert works["parent_works.id"]["display_name"] == "parent work"
    assert works["has_parent_work"]["display_name"] == "has parent work"
    assert works["lineage"]["display_name"] == "work lineage"
    assert works["child_works_count"]["display_name"] == "child works count"
    assert set(works["lineage"]["actions"]) == {"filter", "column"}
    assert {"filter", "sort", "column"} <= set(works["child_works_count"]["actions"])
    assert "group_by" in works["parent_works.id"]["actions"]
    assert "volume" not in works and "volume.id" not in works


def test_volume_requests_answer_a_json_400(client):
    for url in ("/works?filter=volume.id:W3109397498", "/works?group_by=volume.id", "/works?sort=volume.id",
                "/works?select=id,volume", "/works/W3109397498?select=volume"):
        r = client.get(url)
        assert r.status_code in (400, 403), (url, r.status_code)
        body = r.get_json()
        assert "volume was retired on 14 November 2026" in body["message"], (url, body)
        assert "parent_works" in body["message"]
