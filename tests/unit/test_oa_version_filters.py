"""has_oa_submitted_version / has_oa_accepted_or_published_version need ONE copy that is both open and of that
version (oxjob #2642). locations_full is not nested in Elasticsearch, so the old two-term test (some copy open, some
copy of that version) also matches works whose open copy and versioned copy differ. It never misses a true work, so
the filter keeps it and drops the works whose stored answer (an internal boolean sync_works writes) is false.
No ES needed: these assert on the queries the code builds.
"""
from elasticsearch_dsl import Search

from core.filter import filter_records
from core.group_by.buckets import create_group_by_buckets
from works.fields import fields_dict as works_fields

VERSIONS = {
    "has_oa_submitted_version": ["submittedVersion"],
    "has_oa_accepted_or_published_version": ["acceptedVersion", "publishedVersion"],
}


def true_query(param):
    return {"bool": {
        "filter": [
            {"term": {"locations_full.is_oa": "true"}},
            {"terms": {"locations_full.version": VERSIONS[param]}},
        ],
        "must_not": [{"term": {param: False}}],
    }}


def filter_clause(param, value):
    body = filter_records(works_fields, [{param: value}], Search()).to_dict()
    return body["query"]["bool"]["filter"][0]


def test_true_is_the_two_term_test_minus_stored_false():
    for param in VERSIONS:
        assert filter_clause(param, "true") == true_query(param), param


def false_query(param):
    # NOT (open AND version AND NOT stored false): elasticsearch_dsl writes it as one of the three negated
    return {"bool": {"should": [
        {"bool": {"must_not": [{"term": {"locations_full.is_oa": "true"}}]}},
        {"bool": {"must_not": [{"terms": {"locations_full.version": VERSIONS[param]}}]}},
        {"term": {param: False}},
    ]}}


def test_false_is_the_negation_of_true():
    for param in VERSIONS:
        assert filter_clause(param, "false") == false_query(param), param


def test_group_by_counts_what_the_filter_matches():
    params = {"per_page": 200, "cursor": None, "q": None, "sort": None}
    for param in VERSIONS:
        aggs = create_group_by_buckets(works_fields, param, False, Search(), params).to_dict()["aggs"]
        filters = next(iter(aggs.values()))["filters"]["filters"]
        assert filters["true"] == true_query(param), param
        assert filters["false"] == false_query(param), param


def test_stored_answer_is_never_served():
    from works.schemas import WorksSchema
    assert not set(VERSIONS) & set(WorksSchema().fields), "the internal booleans must stay out of the API response"
