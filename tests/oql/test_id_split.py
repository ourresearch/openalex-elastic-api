"""Big id filters run in pieces and merge exactly (oxjob #1617)."""
from query_translation import id_split as S

IDS = [f"https://openalex.org/W{i}" for i in range(100_000)]


def body(aggs=None, **extra):
    b = {"size": 0, "track_total_hits": True,
         "query": {"bool": {"filter": [
             {"bool": {"should": [{"terms": {"id": IDS[:60_000]}},
                                  {"terms": {"id": IDS[60_000:]}}],
                       "minimum_should_match": 1}},
             {"term": {"is_xpac": "false"}}]}}}
    if aggs:
        b["aggs"] = aggs
    b.update(extra)
    return b


def test_pieces_are_disjoint_and_cover_the_ids():
    pieces = S.plan(body())
    assert len(pieces) == 3
    seen = []
    for p in pieces:
        f = p["query"]["bool"]["filter"]
        assert f[1] == {"term": {"is_xpac": "false"}}
        seen += f[0]["terms"]["id"]
    assert sorted(seen) == sorted(IDS)


def test_small_filters_and_hits_run_whole():
    small = body()
    small["query"]["bool"]["filter"][0] = {"terms": {"id": IDS[:1000]}}
    assert S.plan(small) is None
    assert S.plan(body(size=10)) is None
    assert S.plan(body(sort=[{"id": "asc"}])) is None
    assert S.plan(body({"m": {"avg": {"field": "fwci"}}})) is None
    assert S.plan(body({"s0": {"terms": {"field": "type", "min_doc_count": 5}}})) is None
    nested = {"s0": {"terms": {"field": "publication_year"},
                     "aggs": {"s1": {"terms": {"field": "type"}}}}}
    assert S.plan(body(nested)) is None


def test_pieces_list_every_key():
    aggs = {"s0": {"terms": {"field": "type", "size": 2, "shard_size": 50},
                   "aggs": {"c": {"sum": {"field": "cited_by_count"}}}},
            "n_groups": {"cardinality": {"field": "type", "precision_threshold": 3000}}}
    p = S.plan(body(aggs))[0]["aggs"]
    assert p["s0"]["terms"] == {"field": "type", "size": S.PIECE_KEYS}
    assert "n_groups" not in p   # counted from s0's keys


def test_a_lone_count_of_groups_lists_its_keys():
    p = S.plan(body({"n": {"cardinality": {"field": "primary_location.source.id"}}}))[0]
    assert p["aggs"] == {"n": {"terms": {"field": "primary_location.source.id",
                                          "size": S.PIECE_KEYS}}}


def test_fields_a_work_holds_many_of_run_whole():
    for field in ("authorships.author.id", "referenced_works", "topics.id"):
        assert S.plan(body({"s0": {"terms": {"field": field}}})) is None
        assert S.plan(body({"n": {"cardinality": {"field": field}}})) is None


def test_the_filter_is_found_inside_an_and():
    b = body()
    idf = b["query"]["bool"]["filter"][0]
    b["query"] = {"bool": {"filter": [{"bool": {"must": [{"range": {"publication_year": {"gte": 2020}}},
                                                          idf]}}]}}
    pieces = S.plan(b)
    assert len(pieces) == 3
    inner = pieces[0]["query"]["bool"]["filter"][0]["bool"]["must"]
    assert inner[0] == {"range": {"publication_year": {"gte": 2020}}}
    assert len(inner[1]["terms"]["id"]) in (33_333, 33_334)
    assert b["query"]["bool"]["filter"][0]["bool"]["must"][1] is idf   # the body is untouched


def test_no_split_inside_a_pool():
    seen = S._pmap(lambda _: S.plan(body()), [1, 2])
    assert seen == [None, None]
    assert S.plan(body()) is not None


def resp(total, buckets, rest=0):
    aggs = {"s0": {"sum_other_doc_count": rest,
                   "buckets": [{"key": k, "doc_count": n, "c": {"value": c}} for k, n, c in buckets]},
            "n_groups": {"sum_other_doc_count": 0,
                         "buckets": [{"key": k, "doc_count": n} for k, n, _ in buckets]}}
    return {"took": 5, "hits": {"total": {"value": total, "relation": "eq"}}, "aggregations": aggs}


AGGS = {"s0": {"terms": {"field": "type", "size": 2},
               "aggs": {"c": {"sum": {"field": "cited_by_count"}}}},
        "n_groups": {"cardinality": {"field": "type"}}}


def test_merge_adds_counts_sorts_and_cuts():
    out = S.merge(body(AGGS), [resp(10, [("article", 6, 60), ("book", 4, 4)]),
                               resp(9, [("article", 5, 50), ("review", 4, 40)])])
    assert out["hits"]["total"] == {"value": 19, "relation": "eq"}
    s0 = out["aggregations"]["s0"]
    assert [(b["key"], b["doc_count"], b["c"]["value"]) for b in s0["buckets"]] == [
        ("article", 11, 110), ("book", 4, 4)]   # count ties break by key
    assert s0["sum_other_doc_count"] == 4
    assert out["aggregations"]["n_groups"] == {"value": 3}


def test_merge_orders_by_a_metric_with_empty_groups_last():
    aggs = {"s0": {"terms": {"field": "type", "size": 5, "order": [{"c": "desc"}]},
                   "aggs": {"c": {"max": {"field": "fwci"}}}}}
    r1 = {"took": 1, "hits": {"total": {"value": 3}}, "aggregations": {"s0": {
        "sum_other_doc_count": 0, "buckets": [{"key": "a", "doc_count": 1, "c": {"value": None}},
                                              {"key": "b", "doc_count": 1, "c": {"value": 2.0}}]}}}
    r2 = {"took": 1, "hits": {"total": {"value": 1}}, "aggregations": {"s0": {
        "sum_other_doc_count": 0, "buckets": [{"key": "b", "doc_count": 1, "c": {"value": 5.0}},
                                              {"key": "c", "doc_count": 1, "c": {"value": 3.0}}]}}}
    out = S.merge(body(aggs), [r1, r2])
    assert [b["key"] for b in out["aggregations"]["s0"]["buckets"]] == ["b", "c", "a"]


def test_a_full_piece_means_run_whole():
    calls = []

    def run_one(piece):
        calls.append(piece)
        return resp(5, [("article", 5, 5)], rest=1)   # a piece that couldn't list every key
    assert S.search(run_one, body(AGGS)) is None
    assert len(calls) == 3


def test_filter_wrapping_merges():
    aggs = {"pushed": {"filter": {"term": {"primary_location.source.type": "journal"}},
                       "aggs": AGGS}}
    pieces = S.plan(body(aggs))
    assert pieces and "pushed" in pieces[0]["aggs"]
    r = [{"took": 1, "hits": {"total": {"value": 10, "relation": "eq"}},
          "aggregations": {"pushed": dict(doc_count=8, **resp(8, [("x", 8, 1)])["aggregations"])}}
         for _ in pieces]
    out = S.merge(body(aggs), r)
    assert out["aggregations"]["pushed"]["doc_count"] == 8 * len(pieces)
    assert out["aggregations"]["pushed"]["s0"]["buckets"][0]["doc_count"] == 8 * len(pieces)
