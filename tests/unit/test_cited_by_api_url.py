"""`cited_by_api_url` on works (oxjob #1046, Zendesk 6184, 6138, 6191).

v1 gave every work `cited_by_api_url`, the API query for the works that cite it
(`https://api.openalex.org/works?filter=cites:W...`). Walden's ES and Lakebase work docs don't carry it, so the key
vanished from every response with data version 2 (Nov 2025) while `select=cited_by_api_url` still accepted it. It is
now computed from the work's own id. No ES needed.
"""
from elasticsearch_dsl.utils import AttrDict

from works.lakebase import LakebaseHit
from works.schemas import WorksSchema

URL = "https://api.openalex.org/works?filter=cites:W2072212447"


def work_doc(**extra):
    return AttrDict({"id": "https://openalex.org/W2072212447", "cited_by_count": 114, **extra})


ONLY = ("id", "cited_by_count", "cited_by_api_url")


def test_list_work_carries_cited_by_api_url():
    out = WorksSchema(context={}, only=ONLY).dump(work_doc())
    assert out["cited_by_api_url"] == URL


def test_single_work_carries_cited_by_api_url():
    out = WorksSchema(context={"single_record": True}, only=ONLY).dump(work_doc())
    assert out["cited_by_api_url"] == URL


def test_lakebase_single_work_carries_cited_by_api_url():
    hit = LakebaseHit({"id": "https://openalex.org/W2072212447"})
    out = WorksSchema(context={"single_record": True}, only=("id", "cited_by_api_url")).dump(hit)
    assert out["cited_by_api_url"] == URL


def test_select_only_cited_by_api_url_still_computes_it():
    out = WorksSchema(context={}, only=("id", "cited_by_api_url")).dump(work_doc())
    assert out == {"id": "https://openalex.org/W2072212447", "cited_by_api_url": URL}


def test_a_stored_value_is_ignored_for_the_computed_one():
    # an old doc that still carried the Logstash value gets the same canonical query
    out = WorksSchema(context={}, only=("cited_by_api_url",)).dump(
        work_doc(cited_by_api_url="https://api.openalex.org/works?filter=cites:W1")
    )
    assert out["cited_by_api_url"] == URL


def test_doc_without_id_gives_null():
    assert WorksSchema(context={}, only=("cited_by_api_url",)).dump(AttrDict({}))["cited_by_api_url"] is None


def test_key_sits_where_v1_put_it():
    declared = list(WorksSchema._declared_fields)
    assert declared.index("cited_by_api_url") == declared.index("abstract_inverted_index") + 1
    assert declared.index("counts_by_year") == declared.index("cited_by_api_url") + 1
