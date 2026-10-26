"""Semantic search honours the corpus (oxjob #1649).

The vector index holds core and xpac works alike and has no is_xpac field, so the corpus filter (corpus=core is the
/works default, is_xpac:false) is checked on the works index over a wider pool of nearest works. It used to be
dropped, so the default semantic search returned xpac works and corpus=expansion returned core works.
"""
import pytest

from core import vector_index
from core.vector_index import _pop_corpus_clause


@pytest.mark.parametrize(
    "value, clause",
    [
        ("false", {"term": {"is_xpac": False}}),
        ("true", {"term": {"is_xpac": True}}),
        ("!true", {"term": {"is_xpac": False}}),
        ("!false", {"term": {"is_xpac": True}}),
        ("true|false", None),
        ("FALSE", {"term": {"is_xpac": False}}),
    ],
)
def test_corpus_clause_from_the_url_value(value, clause):
    params = {"filters": [{"type": "article"}, {"is_xpac": value}]}
    assert _pop_corpus_clause(params) == clause
    assert params["filters"] == [{"type": "article"}]


def test_no_corpus_filter_leaves_filters_alone():
    params = {"filters": [{"type": "article"}]}
    assert _pop_corpus_clause(params) is None and params["filters"] == [{"type": "article"}]
    assert _pop_corpus_clause({"filters": None}) is None


def test_contradictory_corpus_filters_match_nothing():
    clause = _pop_corpus_clause({"filters": [{"is_xpac": "true"}, {"is_xpac": "false"}]})
    assert clause == {"bool": {"must_not": [{"match_all": {}}]}}


def _wid(n):
    return f"https://openalex.org/W{n}"


class _CorpusES:
    """Vector index: the n-th nearest work is W{n}; a post_filter keeps `per_1000` of every 1,000 pooled works.
    Works index: W{n} is xpac when xpac(n)."""

    def __init__(self, xpac, per_1000=1000, available=10**6):
        self.xpac, self.per_1000, self.available, self.calls = xpac, per_1000, available, []

    def search(self, index, body):
        if index == vector_index.settings.WORKS_INDEX:
            ids_clause, corpus = body["query"]["bool"]["filter"]
            ids = ids_clause["ids"]["values"]
            want = corpus["term"]["is_xpac"]
            self.calls.append(("corpus", len(ids)))
            return {"hits": {"hits": [{"_id": i} for i in ids if self.xpac(int(i.rsplit("W", 1)[1])) == want]}}
        knn = body["knn"]
        if "post_filter" in body:
            pool = knn["k"]
            self.calls.append(("post", pool))
            n = min(body["size"], self.per_1000 * pool // 1000, self.available)
            return {"hits": {"hits": [{"_id": _wid(i), "_score": 0.9} for i in range(n)]},
                    "aggregations": {"pool": {"value": min(pool, self.available)}}}
        self.calls.append(("knn", knn["k"]))
        n = min(knn["k"], self.available)
        return {"hits": {"hits": [{"_id": _wid(i), "_score": 0.9} for i in range(n)]}}


def _run(monkeypatch, es, filters):
    hydrated = {}

    def fake_hydrate(results, connection="walden", works_filter=None):
        hydrated["works_filter"] = works_filter
        return [{"_id": r[0]} for r in results]

    monkeypatch.setattr(vector_index.connections, "get_connection", lambda alias: es)
    monkeypatch.setattr(vector_index, "embed_query", lambda text: [0.1] * 4)
    monkeypatch.setattr(vector_index, "hydrate_results", fake_hydrate)
    # Other unit tests leave a stub `settings` module behind; set what this path reads.
    for name, value in (("SEMANTIC_TEXT_BOOST", False), ("WORKS_INDEX", "works"), ("WORKS_VECTOR_INDEX", "works-vectors"),
                        ("VECTOR_NUM_CANDIDATES", 300), ("VECTOR_EXACT_MAX_MATCHES", 0),
                        ("VECTOR_PREFILTER_VISIT_PERCENTAGE", 0)):
        monkeypatch.setattr(vector_index.settings, name, value, raising=False)
    result = vector_index.vector_semantic_search({"search": "q", "filters": filters, "per_page": 50}, "works", "walden")
    return [o.meta.id for o in result["results"]], hydrated["works_filter"]


def test_default_core_drops_xpac_from_a_pool_of_300(monkeypatch):
    es = _CorpusES(xpac=lambda n: n % 5 == 0)   # a fifth of the nearest works are xpac
    ids, works_filter = _run(monkeypatch, es, [{"is_xpac": "false"}])
    assert len(ids) == 50 and not any(int(i.rsplit("W", 1)[1]) % 5 == 0 for i in ids)
    assert es.calls == [("knn", 300), ("corpus", 300)]
    assert works_filter == {"bool": {"must": [{"term": {"is_xpac": False}}]}}


def test_xpac_heavy_query_widens_to_1000(monkeypatch):
    es = _CorpusES(xpac=lambda n: n % 10 != 0)  # 9 in 10 nearest are xpac: 30 core in 300, 100 in 1,000
    ids, _ = _run(monkeypatch, es, [{"is_xpac": "false"}])
    assert len(ids) == 50
    assert es.calls == [("knn", 300), ("corpus", 300), ("knn", 1000), ("corpus", 1000)]


def test_expansion_keeps_only_xpac(monkeypatch):
    es = _CorpusES(xpac=lambda n: n % 2 == 0)
    ids, _ = _run(monkeypatch, es, [{"is_xpac": "true"}])
    assert len(ids) == 50 and all(int(i.rsplit("W", 1)[1]) % 2 == 0 for i in ids)


def test_corpus_all_is_unchanged(monkeypatch):
    es = _CorpusES(xpac=lambda n: True)
    ids, works_filter = _run(monkeypatch, es, None)
    assert len(ids) == 50 and es.calls == [("knn", 50)] and works_filter is None


def test_small_pool_returns_what_it_has_without_widening(monkeypatch):
    es = _CorpusES(xpac=lambda n: n % 2 == 0, available=120)  # the similarity floor leaves 120 works
    ids, _ = _run(monkeypatch, es, [{"is_xpac": "false"}])
    assert len(ids) == 50 and es.calls == [("knn", 300), ("corpus", 120)]


def test_corpus_does_not_push_a_year_filter_onto_the_pre_filter(monkeypatch):
    # A single year keeps 15 in 1,000 (the oxjob #1433 case that tries the 5,000 pool); a fifth of them are xpac.
    es = _CorpusES(xpac=lambda n: n % 5 == 0, per_1000=15)
    ids, works_filter = _run(monkeypatch, es, [{"publication_year": "2025"}, {"is_xpac": "false"}])
    assert len(ids) == 50
    assert es.calls == [("post", 1000), ("corpus", 15), ("post", 5000), ("corpus", 75)]
    assert works_filter == {"bool": {"must": [{"term": {"publication_year": 2025}}, {"term": {"is_xpac": False}}]}}


def test_id_filter_with_corpus_stays_pre_filtered(monkeypatch):
    es = _CorpusES(xpac=lambda n: n % 5 == 0)
    ids, _ = _run(monkeypatch, es, [{"authorships.author.id": "A1"}, {"is_xpac": "false"}])
    assert len(ids) == 50 and es.calls == [("knn", 300), ("corpus", 300)]
