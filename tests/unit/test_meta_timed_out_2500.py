"""oxjob #2500: a search Elasticsearch cut off at the 5 s soft timeout (core/shared_view.py, oxjob #521) returns a
partial count. #521 sets meta["timed_out"] = True for it, but MetaSchema did not declare the key, and marshmallow
drops undeclared keys on dump, so the flag never reached a response: the same heavy query came back with a different
meta.count each run (ZD 28095: 931, 958, 955) and nothing said the count was incomplete. No ES. Run with --noconftest."""
from elasticsearch_dsl import Search
from elasticsearch_dsl.response import Response

from core.schemas import MetaSchema
from core.shared_view import format_meta
from works.schemas import MessageSchema as WorksMessageSchema

PARAMS = {"page": 1, "per_page": 1, "group_by": None, "group_bys": None, "cursor": None, "sample": None, "q": None}


def _response(timed_out):
    return Response(Search(), {"took": 5071, "timed_out": timed_out,
                               "_shards": {"total": 1, "successful": 1, "skipped": 0, "failed": 0},
                               "hits": {"total": {"value": 931, "relation": "eq"}, "max_score": None, "hits": []}})


def test_a_timed_out_search_says_so_in_meta():
    meta = MetaSchema().dump(format_meta(_response(True), PARAMS, None))
    assert meta["timed_out"] is True
    assert meta["count"] == 931


def test_a_complete_search_carries_no_timed_out_key():
    meta = MetaSchema().dump(format_meta(_response(False), PARAMS, None))
    assert "timed_out" not in meta  # additive: responses that finished are byte-for-byte as before


def test_the_flag_survives_the_works_envelope():
    # the /works and OQL (POST /, GET /?oql=) paths both dump through the entity's MessageSchema
    out = WorksMessageSchema().dump({"meta": format_meta(_response(True), PARAMS, None), "results": [],
                                     "group_by": []})
    assert out["meta"]["timed_out"] is True
