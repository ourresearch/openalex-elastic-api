"""Works location filters read `locations_full` (oxjob #1673).

ES caps a work's `locations` at 100 for list views and keeps every location in
`locations_full`, as with authorships / authorships_full. Filters, group_bys and
sorts must read `locations_full` so a match past position 100 is still found;
single-record responses show `locations_full`; list responses never ship it.
No ES needed: these assert on the queries and responses the code builds.
"""
import json
import re

from elasticsearch_dsl import Search
from elasticsearch_dsl.utils import AttrDict

from core.filter import filter_records
from core.group_by.buckets import create_group_by_buckets
from core.shared_view import set_source
from works.fields import fields_dict as works_fields
from works.schemas import WorksSchema

CAPPED = re.compile(r'"locations\.')
FULL = re.compile(r'"locations_full\.')

SAMPLE_VALUES = {
    "BooleanField": ["true", "false", "null", "!null"],
    "OpenAlexIDField": ["S4306400194", "!S4306400194", "S4306400194|S190740074", "null", "!null"],
    "TermField": ["cc-by", "!cc-by", "cc-by|cc-by-nc", "null|cc-by", "null", "!null"],
}
LOCATION_PARAMS = [
    "best_open_version", "doi", "has_oa_accepted_or_published_version", "has_oa_submitted_version", "has_pdf_url",
    "locations.is_accepted", "locations.is_oa", "locations.is_published", "locations.landing_page_url",
    "locations.license", "locations.license_id", "locations.raw_type", "locations.source.has_issn",
    "locations.source.host_organization", "locations.source.host_organization_lineage", "locations.source.id",
    "locations.source.is_core", "locations.source.is_in_doaj", "locations.source.is_oa", "locations.source.issn",
    "locations.source.listed_in", "locations.source.type", "locations.version", "repository", "version",
]


def filter_body(param, value):
    return json.dumps(filter_records(works_fields, [{param: value}], Search()).to_dict())


def group_by_body(param):
    params = {"per_page": 200, "cursor": None, "q": None, "sort": None}
    return create_group_by_buckets(works_fields, param, False, Search(), params).to_dict()


def test_no_works_filter_reads_capped_locations():
    """Any works field, any operator: no query may touch `locations.*` (it holds the first 100 only)."""
    for param, field in works_fields.items():
        for value in SAMPLE_VALUES.get(type(field).__name__, []):
            try:
                body = filter_body(param, value)
            except Exception:
                continue  # value not valid for this field
            assert not CAPPED.search(body), (param, value, body)


VALID_VALUE = {"doi": "10.1038/nature14539", "best_open_version": "published", "version": "acceptedVersion",
               "locations.version": "acceptedVersion"}


def test_every_location_filter_reads_locations_full():
    for param in LOCATION_PARAMS:
        value = VALID_VALUE.get(param) or SAMPLE_VALUES[type(works_fields[param]).__name__][0]
        assert FULL.search(filter_body(param, value)), param


def test_doi_matches_any_location_doi_in_locations_full():
    body = json.loads(filter_body("doi", "10.3929/ethz-b-000667478"))
    should = body["query"]["bool"]["filter"][0]["bool"]["should"]
    assert {"term": {"locations_full.doi.lower": "https://doi.org/10.3929/ethz-b-000667478"}} in should


def test_repository_filter_and_negation():
    pos = json.loads(filter_body("repository", "S4306400194"))["query"]["bool"]["filter"][0]
    assert pos == {"bool": {"must": [
        {"term": {"locations_full.source.id": "https://openalex.org/S4306400194"}},
        {"term": {"locations_full.source.type": "repository"}},
    ]}}
    neg = json.loads(filter_body("repository", "!S4306400194"))["query"]["bool"]["filter"][0]
    assert neg == {"bool": {"must_not": [{"term": {"locations_full.source.id": "https://openalex.org/S4306400194"}}]}}


def test_boolean_null_uses_locations_full():
    body = json.loads(filter_body("locations.is_oa", "null"))
    assert body["query"]["bool"]["filter"][0] == {"bool": {"must_not": [{"exists": {"field": "locations_full.is_oa"}}]}}


def test_term_filter_keeps_lower_subfield():
    body = json.loads(filter_body("locations.source.type", "repository"))
    assert body["query"]["bool"]["filter"][0] == {"term": {"locations_full.source.type.lower": "repository"}}


def test_group_by_aggregates_raw_locations_full_field():
    """Group by the keyword field itself, not `.lower`: bucket keys keep their case."""
    for param, agg_field in [
        ("locations.source.type", "locations_full.source.type"),
        ("locations.source.id", "locations_full.source.id"),
        ("locations.license", "locations_full.license_id.keyword"),
    ]:
        aggs = group_by_body(param)["aggs"]
        assert next(iter(aggs.values()))["terms"]["field"] == agg_field, param


def test_group_by_repository_restricts_to_repository_locations():
    body = group_by_body("repository")
    assert body["query"]["bool"]["filter"] == [{"term": {"locations_full.source.type": "repository"}}]
    assert body["aggs"]["groupby_repository"]["terms"]["field"] == "locations_full.source.id"


def test_sort_field_reads_locations_full():
    assert works_fields["locations.source.id"].es_sort_field() == "locations_full.source.id"
    assert works_fields["locations.version"].es_sort_field() == "locations_full.version"
    assert works_fields["locations.is_oa"].es_sort_field() == "locations_full.is_oa"


def test_list_views_exclude_locations_full():
    excludes = set_source("works", Search()).to_dict()["_source"]["excludes"]
    assert "locations_full" in excludes and "authorships_full" in excludes


def work_doc(n_full, n_shown, locations_count=None):
    full = [{"provenance": "mag", "native_id": str(i), "is_oa": False} for i in range(n_full)]
    return AttrDict({
        "id": "https://openalex.org/W1",
        "locations": full[:n_shown],
        "locations_full": full,
        "locations_count": n_full if locations_count is None else locations_count,
    })


def test_single_record_shows_locations_full():
    out = WorksSchema(context={"single_record": True}, only=("id", "locations", "locations_count")).dump(work_doc(150, 100))
    assert len(out["locations"]) == 150 and out["locations_count"] == 150


def test_list_record_keeps_capped_locations_and_true_count():
    out = WorksSchema(context={}, only=("id", "locations", "locations_count")).dump(work_doc(150, 100))
    assert len(out["locations"]) == 100 and out["locations_count"] == 150


def test_scrub_on_capped_list_adjusts_count_and_leaves_oa(monkeypatch):
    monkeypatch.setitem(WorksSchema.scrub_bad_locations.__globals__["SCRUBBED_WORK_LOCATIONS"],
                        "https://openalex.org/W1", {"mag:3"})
    doc = work_doc(150, 100)
    doc["open_access"] = {"is_oa": True, "oa_status": "green", "oa_url": "x", "any_repository_has_fulltext": True}
    out = WorksSchema(context={}, only=("id", "locations", "locations_count", "open_access")).dump(doc)
    assert len(out["locations"]) == 99 and out["locations_count"] == 149
    assert out["open_access"]["is_oa"] is True  # an OA location may sit past position 100


def test_scrub_on_complete_list_still_forces_closed(monkeypatch):
    monkeypatch.setitem(WorksSchema.scrub_bad_locations.__globals__["SCRUBBED_WORK_LOCATIONS"],
                        "https://openalex.org/W1", {"mag:3"})
    doc = work_doc(5, 5)
    doc["open_access"] = {"is_oa": True, "oa_status": "green", "oa_url": "x", "any_repository_has_fulltext": True}
    out = WorksSchema(context={}, only=("id", "locations", "locations_count", "open_access")).dump(doc)
    assert len(out["locations"]) == 4 and out["locations_count"] == 4
    assert out["open_access"]["is_oa"] is False


def test_scrub_without_locations_selected_still_forces_closed(monkeypatch):
    monkeypatch.setitem(WorksSchema.scrub_bad_locations.__globals__["SCRUBBED_WORK_LOCATIONS"],
                        "https://openalex.org/W1", {"mag:3"})
    doc = work_doc(150, 100)
    doc["open_access"] = {"is_oa": True, "oa_status": "green", "oa_url": "x", "any_repository_has_fulltext": True}
    out = WorksSchema(context={}, only=("id", "locations_count", "open_access")).dump(doc)
    assert out["locations_count"] == 150 and out["open_access"]["is_oa"] is False  # unchanged from before #1673
