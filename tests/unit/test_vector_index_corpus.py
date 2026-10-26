"""Semantic search honours the corpus (oxjob #1649).

The vector index holds core and xpac works alike and has no is_xpac field, so the corpus filter (corpus=core is the
/works default, is_xpac:false) is checked on the works index over a wider pool of nearest works. It used to be
dropped, so the default semantic search returned xpac works and corpus=expansion returned core works.
"""
import pytest

from core import vector_index
from core.exceptions import APIQueryParamsError
from core.vector_index import _pop_corpus_clause


def test_corpus_clause_is_the_query_works_builds():
    params = {"filters": [{"type": "article"}, {"is_xpac": "false"}]}
    assert _pop_corpus_clause(params) == {"bool": {"filter": [{"term": {"is_xpac": "false"}}]}}
    assert params["filters"] == [{"type": "article"}]
    assert _pop_corpus_clause({"filters": [{"is_xpac": "null"}]}) == {
        "bool": {"filter": [{"bool": {"must_not": [{"exists": {"field": "is_xpac"}}]}}]}}


def test_bad_corpus_value_is_a_400_as_on_works():
    with pytest.raises(APIQueryParamsError):
        _pop_corpus_clause({"filters": [{"is_xpac": "yes"}]})


def test_no_corpus_filter_leaves_filters_alone():
    params = {"filters": [{"type": "article"}]}
    assert _pop_corpus_clause(params) is None and params["filters"] == [{"type": "article"}]
    assert _pop_corpus_clause({"filters": None}) is None


def _wid(n):
    return f"https://openalex.org/W{n}"


def _wanted_xpac(clause):
    """The is_xpac value a works-index filter asks for (the fake checks only that clause)."""
    if isinstance(clause, dict):
        term = clause.get("term", {})
        if "is_xpac" in term:
            return str(term["is_xpac"]).lower() == "true"
        for v in clause.values():
            found = _wanted_xpac(v)
            if found is not None:
                return found
    if isinstance(clause, list):
        for v in clause:
            found = _wanted_xpac(v)
            if found is not None:
                return found
    return None


class _CorpusES:
    """Vector index: the n-th nearest work is W{n}; a post_filter keeps `per_1000` of every 1,000 pooled works.
    Works index: W{n} is xpac when xpac(n)."""

    def __init__(self, xpac, per_1000=1000, available=10**6):
        self.xpac, self.per_1000, self.available, self.calls = xpac, per_1000, available, []

    def search(self, index, body):
        if index == vector_index.settings.WORKS_INDEX:
            ids_clause, works_filter = body["query"]["bool"]["filter"]
            ids = ids_clause["ids"]["values"]
            want = _wanted_xpac(works_filter)
            self.calls.append(("check", len(ids)))
            return {"hits": {"hits": [{"_id": i} for i in ids if self.xpac(int(i.rsplit("W", 1)[1])) == want]}}
        if "knn" not in body:   # the exact path: script_score over the pre-filter's matches
            self.calls.append(("exact", body["size"]))
            n = min(body["size"], self.available)
            return {"hits": {"hits": [{"_id": _wid(i), "_score": 0.9} for i in range(n)]}}
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


class _CountingCorpusES(_CorpusES):
    """Answers the pre-filter's capped count with `matches` (decides exact path vs filtered kNN)."""

    def __init__(self, matches, **kw):
        super().__init__(**kw)
        self.matches = matches

    def search(self, index, body):
        if body.get("size") == 0:
            return {"hits": {"total": {"value": min(self.matches, body["track_total_hits"]), "relation": "eq"}}}
        return super().search(index, body)


def _run(monkeypatch, es, filters, exact_max=0):
    hydrated = {}

    def fake_hydrate(results, connection="walden", works_filter=None):
        hydrated["works_filter"] = works_filter
        return [{"_id": r[0]} for r in results]

    monkeypatch.setattr(vector_index.connections, "get_connection", lambda alias: es)
    monkeypatch.setattr(vector_index, "embed_query", lambda text: [0.1] * 4)
    monkeypatch.setattr(vector_index, "hydrate_results", fake_hydrate)
    # Other unit tests leave a stub `settings` module behind; set what this path reads.
    for name, value in (("SEMANTIC_TEXT_BOOST", False), ("WORKS_INDEX", "works"), ("WORKS_VECTOR_INDEX", "works-vectors"),
                        ("VECTOR_NUM_CANDIDATES", 300), ("VECTOR_EXACT_MAX_MATCHES", exact_max),
                        ("VECTOR_PREFILTER_VISIT_PERCENTAGE", 0)):
        monkeypatch.setattr(vector_index.settings, name, value, raising=False)
    result = vector_index.vector_semantic_search({"search": "q", "filters": filters, "per_page": 50}, "works", "walden")
    return [o.meta.id for o in result["results"]], hydrated["works_filter"]


def _n(wid):
    return int(wid.rsplit("W", 1)[1])


def test_default_core_drops_xpac_from_a_pool_of_100(monkeypatch):
    es = _CorpusES(xpac=lambda n: n % 5 == 0)   # a fifth of the nearest works are xpac
    ids, hydrate_filter = _run(monkeypatch, es, [{"is_xpac": "false"}])
    assert len(ids) == 50 and not any(_n(i) % 5 == 0 for i in ids)
    assert es.calls == [("knn", 100), ("check", 100)]
    assert hydrate_filter is None   # already checked; hydration is a plain mget


def test_xpac_heavy_query_widens_to_1000(monkeypatch):
    es = _CorpusES(xpac=lambda n: n % 10 != 0)  # 9 in 10 nearest are xpac: 10 core in 100, 100 in 1,000
    ids, _ = _run(monkeypatch, es, [{"is_xpac": "false"}])
    assert len(ids) == 50
    assert es.calls == [("knn", 100), ("check", 100), ("knn", 1000), ("check", 1000)]


def test_expansion_keeps_only_xpac(monkeypatch):
    es = _CorpusES(xpac=lambda n: n % 2 == 0)
    ids, _ = _run(monkeypatch, es, [{"is_xpac": "true"}])
    assert len(ids) == 50 and all(_n(i) % 2 == 0 for i in ids)


def test_corpus_all_is_unchanged(monkeypatch):
    es = _CorpusES(xpac=lambda n: True)
    ids, hydrate_filter = _run(monkeypatch, es, None)
    assert len(ids) == 50 and es.calls == [("knn", 50)] and hydrate_filter is None


def test_small_pool_returns_what_it_has_without_widening(monkeypatch):
    es = _CorpusES(xpac=lambda n: n % 2 == 0, available=80)  # the similarity floor leaves 80 works
    ids, _ = _run(monkeypatch, es, [{"is_xpac": "false"}])
    assert len(ids) == 40 and es.calls == [("knn", 100), ("check", 80)]


def test_corpus_does_not_push_a_year_filter_onto_the_pre_filter(monkeypatch):
    # A single year keeps 15 in 1,000 (the oxjob #1433 case that tries the 5,000 pool); a fifth of them are xpac.
    es = _CorpusES(xpac=lambda n: n % 5 == 0, per_1000=15)
    ids, _ = _run(monkeypatch, es, [{"publication_year": "2025"}, {"is_xpac": "false"}])
    assert len(ids) == 50
    assert es.calls == [("post", 1000), ("check", 15), ("post", 5000), ("check", 75)]


def test_the_pre_filter_fallback_keeps_what_the_pools_found(monkeypatch):
    # language:ja keeps 3 in 1,000 (too rare for the 5,000 pool), so the search falls back to the pre-filter; the
    # works the pool already found in the corpus stay in the answer.
    class _Fallback(_CorpusES):
        def search(self, index, body):
            if index != "works" and "knn" in body and "post_filter" not in body:
                self.calls.append(("pre", body["knn"]["k"]))
                return {"hits": {"hits": [{"_id": _wid(i), "_score": 0.8} for i in range(100, 150)]}}
            return super().search(index, body)

    es = _Fallback(xpac=lambda n: n % 2 == 0, per_1000=3)
    ids, _ = _run(monkeypatch, es, [{"language": "ja"}, {"is_xpac": "false"}])
    assert es.calls == [("post", 1000), ("check", 3), ("pre", 50), ("check", 50)]
    assert ids[0] == _wid(1) and len(ids) == 26   # W1 from the pool (score 0.9) + 25 odd ids from the pre-filter


def test_the_check_carries_the_users_filters_too(monkeypatch):
    es = _CorpusES(xpac=lambda n: n % 5 == 0, per_1000=15)
    seen = []
    real = es.search

    def spy(index, body):
        if index == "works":
            seen.append(body["query"]["bool"]["filter"][1])
        return real(index, body)

    es.search = spy
    _run(monkeypatch, es, [{"publication_year": "2025"}, {"is_xpac": "false"}])
    assert seen[0] == {"bool": {"must": [{"term": {"publication_year": 2025}},
                                         {"bool": {"filter": [{"term": {"is_xpac": "false"}}]}}]}}


def test_filtered_knn_with_corpus_stays_at_k(monkeypatch):
    # An id filter matching more works than the exact path takes: the filtered kNN costs ~10x at k=300, so it stays at 50.
    es = _CountingCorpusES(matches=900_000, xpac=lambda n: n % 5 == 0)
    ids, _ = _run(monkeypatch, es, [{"authorships.institutions.id": "I1"}, {"is_xpac": "false"}], exact_max=500_000)
    assert es.calls == [("knn", 50), ("check", 50)] and len(ids) == 40


def test_exact_path_with_corpus_widens(monkeypatch):
    es = _CountingCorpusES(matches=20_000, xpac=lambda n: n % 5 == 0)
    ids, _ = _run(monkeypatch, es, [{"authorships.author.id": "A1"}, {"is_xpac": "false"}], exact_max=500_000)
    assert es.calls == [("exact", 1000), ("check", 1000)] and len(ids) == 50
