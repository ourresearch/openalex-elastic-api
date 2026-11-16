"""oxjob #1027: the website's "Export N facets" CSV (`group_bys=...&format=csv`).

- ZD 1493: a `repository` (or `journal`) group among `group_bys` used to filter the
  whole search, so every other group (and meta.count) counted only the works with a
  repository copy (68 of 396 on S2736485060). Its filter now sits inside its own
  aggregation; a single `group_by=repository` is unchanged.
- ZD 3885: the citation / APC sum widgets ride in `group_bys` and answered HTTP 400;
  they are now the meta sums, written as blocks in the CSV.
ES-free: queries via .to_dict(), responses via elasticsearch_dsl's Response on raw dicts.
"""
import csv
import io

from elasticsearch_dsl import Search
from elasticsearch_dsl.response import Response
from flask import Flask

from core.export import export_group_by
from core.group_by.buckets import (create_group_by_buckets, get_default_buckets,
                                   scope_bucket_key)
from core.params import parse_params
from core.shared_view import apply_grouping
from works.fields import fields_dict

REPO_TERM = {"term": {"locations_full.source.type": "repository"}}
PARAMS = {"per_page": 200, "cursor": None, "q": None, "sort": None, "group_by": None}


def _group_bys(keys):
    return apply_grouping({**PARAMS, "group_bys": keys}, fields_dict, Search())


def test_group_bys_repository_filter_stays_in_its_own_aggregation():
    d = _group_bys(["publication_year", "repository"]).to_dict()
    assert "query" not in d                                # no search-level filter
    scope = d["aggs"][scope_bucket_key("repository")]
    assert scope["filter"] == REPO_TERM
    assert "groupby_repository" in scope["aggs"]
    assert "groupby_publication_year" in d["aggs"]          # unscoped, at the root
    assert "groupby_repository" not in d["aggs"]


def test_group_bys_journal_scoped_too():
    d = _group_bys(["type", "journal"]).to_dict()
    assert "query" not in d
    assert d["aggs"][scope_bucket_key("journal")]["filter"] == {
        "term": {"primary_location.source.type": "journal"}}


def test_single_group_by_repository_unchanged():
    s = create_group_by_buckets(fields_dict, "repository", False, Search(), PARAMS)
    d = s.to_dict()
    assert d["query"]["bool"]["filter"] == [REPO_TERM]
    assert "groupby_repository" in d["aggs"]


def test_scoped_buckets_read_back():
    s = _group_bys(["publication_year", "repository"])
    raw = {"hits": {"total": {"value": 396, "relation": "eq"}, "hits": []}, "took": 1,
           "aggregations": {
               "groupby_publication_year": {"buckets": [{"key": 2008, "doc_count": 32}]},
               scope_bucket_key("repository"): {"doc_count": 69, "groupby_repository": {
                   "buckets": [{"key": "https://openalex.org/S1", "doc_count": 8}]}}}}
    r = Response(s, raw)
    assert [(b.key, b.doc_count) for b in get_default_buckets("repository", r)] == [
        ("https://openalex.org/S1", 8)]
    assert [(b.key, b.doc_count) for b in get_default_buckets("publication_year", r)] == [(2008, 32)]


def _parse(qs):
    app = Flask(__name__)
    with app.test_request_context("/works?" + qs):
        from flask import request
        return parse_params(request)


def test_sum_widgets_leave_group_bys_and_become_meta_sums():
    p = _parse("group_bys=cited_by_count_sum,apc_sum,publication_year&format=csv")
    assert p["group_bys"] == ["publication_year"]
    assert p["cited_by_count_sum"] == "true" and p["apc_sum"] == "true"
    plain = _parse("group_bys=publication_year,type")
    assert plain["group_bys"] == ["publication_year", "type"] and plain["cited_by_count_sum"] is None


def test_csv_writes_sum_blocks_first():
    app = Flask(__name__)
    result = {"meta": {"count": 100, "cited_by_count_sum": 1234.0, "apc_list_sum_usd": 5000.0,
                       "apc_paid_sum_usd": 4000.0},
              "group_bys": [{"group_by_key": "publication_year", "groups": [
                  {"key": "2024", "key_display_name": "2024", "doc_count": 60},
                  {"key": "2023", "key_display_name": "2023", "doc_count": 40}]}]}
    with app.test_request_context(
            "/works?group_bys=cited_by_count_sum,apc_sum,publication_year&format=csv"):
        from flask import request
        resp = export_group_by(result, request)
    rows = list(csv.reader(io.StringIO(resp.get_data(as_text=True))))
    assert rows[0][:9] == ["Citations Sum", "", "", "APC Sum", "", "", "Publication Year", "", ""]
    assert rows[2][:2] == ["Citations", "1234"]
    assert rows[2][3:5] == ["APC list price (USD)", "5000"] and rows[3][3:5] == ["APC paid (USD)", "4000"]
    assert rows[2][6:8] == ["2024", "60"] and rows[3][6:8] == ["2023", "40"]


def test_csv_with_only_a_sum():
    app = Flask(__name__)
    with app.test_request_context("/works?group_bys=cited_by_count_sum&format=csv"):
        from flask import request
        resp = export_group_by({"meta": {"count": 3, "cited_by_count_sum": 7}}, request)
    rows = list(csv.reader(io.StringIO(resp.get_data(as_text=True))))
    assert rows[0][0] == "Citations Sum" and rows[2][:2] == ["Citations", "7"]
