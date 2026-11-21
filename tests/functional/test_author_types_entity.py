"""author-types entity wiring (oxjob #2437): human, organization, software-agent, shaped like /relationships.
Uses the tests/conftest `client` fixture; ES is never reached (walden builds author-types-v1).

    PYTHONPATH=. venv/bin/python -m pytest tests/functional/test_author_types_entity.py -q
"""
import pytest
from elasticsearch_dsl import AttrDict

import ids.views
from author_types.schemas import AuthorTypesSchema

VALUES = [("human", "Human"), ("organization", "Organization"), ("software-agent", "Software agent")]


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


@pytest.mark.parametrize("path", ["/author-types/Software-Agent", "/entities/author-types/software-agent"])
def test_single_record_lookup_uses_the_author_types_path_segment(client, monkeypatch, path):
    # index.split("-")[0] would give "author"; the branch in ids/views keeps "author-types"
    _FakeSearch.calls = []
    monkeypatch.setattr(ids.views, "Search", _FakeSearch)
    r = client.get(path)
    assert r.status_code == 404  # fake ES has no docs
    assert b"No author-types found" in r.data
    index, queries = _FakeSearch.calls[-1]
    assert index == "author-types-v1"
    assert queries == [{"term": {"id.lower": "https://openalex.org/author-types/software-agent"}}]


def test_config_route_serves_the_three_values(client):
    r = client.get("/author-types/config")
    assert r.status_code == 200
    assert [(v["id"], v["display_name"]) for v in r.get_json()["values"]] == [
        (f"author-types/{slug}", name) for slug, name in VALUES]


def test_helper_routes(client):
    r = client.get("/author-types/valid_fields")
    assert r.status_code == 200
    assert "works_count" in r.get_json()


def test_the_record_shape():
    terms = [{"vocabulary": "W3C PROV-O", "term": "SoftwareAgent", "url": "http://www.w3.org/ns/prov#SoftwareAgent"},
             {"vocabulary": "Wikidata", "term": "software agent (Q2297769)",
              "url": "https://www.wikidata.org/wiki/Q2297769"}]
    doc = {
        "id": "https://openalex.org/author-types/software-agent", "display_name": "Software agent",
        "description": "Running software that is named as an author: an AI agent or another bot.",
        "standard_terms": terms, "works_count": 7,
        "works_api_url": "https://api.openalex.org/works?filter=authorships.author.type:software-agent",
        "updated_date": "2026-11-21T00:00:00", "created_date": "2026-11-21",
        "cited_by_count": 9,  # not part of the record
    }
    out = AuthorTypesSchema(context={"display_relevance": False}).dump(AttrDict({**doc, "meta": {"score": None}}))
    assert list(out) == ["id", "display_name", "description", "standard_terms", "works_count", "works_api_url",
                         "updated_date", "created_date"]
    assert out["standard_terms"] == terms
    assert list(out["standard_terms"][0]) == ["vocabulary", "term", "url"]


def test_properties_catalog(client):
    props = client.get("/properties").get_json()["properties"]
    assert "author-types" in props
    works = props["works"]["authorships.author.type"]
    assert works["entity_type"] == "author-types"
    assert works["display_name"] == "author type"
    assert {"filter", "group_by"} <= set(works["actions"])
    authors = props["authors"]["type"]
    assert authors["entity_type"] == "author-types"
    assert authors["display_name"] == "author type"
