"""Range-filter grammar on the semantic (vector) pre-filter path — oxjob #862.

The GUI Year chip emits open-ended ranges (``publication_year:2025-``), and the
OQL renderer emits ``N-`` / ``-N`` for ``>=`` / ``<=``. These used to raise a
ValueError inside ``_build_range_filter`` → unhandled → HTML 500 on
``search.semantic`` requests. The vector path must speak the same grammar as
the classic ``RangeField``.
"""
import pytest

from core.exceptions import APIQueryParamsError
from core import vector_index
from core.vector_index import (
    _build_range_filter,
    _translate_filter_for_works,
    build_vector_filter,
    hydrate_results,
)


def rf(value):
    return _build_range_filter("publication_year", "publication_year", value)


@pytest.mark.parametrize(
    "value, expected",
    [
        # the reported bug: "Since 2025" chip preset
        ("2025-", {"range": {"publication_year": {"gte": 2025}}}),
        # end-only custom range (used to be term:-2024 → silently 0 results)
        ("-2024", {"range": {"publication_year": {"lte": 2024}}}),
        (">2020", {"range": {"publication_year": {"gt": 2020}}}),
        ("<2020", {"range": {"publication_year": {"lt": 2020}}}),
        (">=2020", {"range": {"publication_year": {"gte": 2020}}}),
        ("<=2020", {"range": {"publication_year": {"lte": 2020}}}),
        ("2021-2026", {"range": {"publication_year": {"gte": 2021, "lte": 2026}}}),
        ("2021", {"term": {"publication_year": 2021}}),
        (" 2021 ", {"term": {"publication_year": 2021}}),
        ("null", {"bool": {"must_not": [{"exists": {"field": "publication_year"}}]}}),
    ],
)
def test_range_grammar_matches_classic(value, expected):
    assert rf(value) == expected


def test_pipe_or_of_ranges():
    assert rf("2021|2022") == {
        "bool": {
            "should": [
                {"term": {"publication_year": 2021}},
                {"term": {"publication_year": 2022}},
            ],
            "minimum_should_match": 1,
        }
    }
    assert rf("2010-2012|2020-") == {
        "bool": {
            "should": [
                {"range": {"publication_year": {"gte": 2010, "lte": 2012}}},
                {"range": {"publication_year": {"gte": 2020}}},
            ],
            "minimum_should_match": 1,
        }
    }


def test_single_value_with_trailing_pipe_collapses():
    assert rf("2021|") == {"term": {"publication_year": 2021}}


@pytest.mark.parametrize("value", ["abc", "20x1-", "-", "|", "2020-abc", ">"])
def test_garbage_is_400_not_500(value):
    with pytest.raises(APIQueryParamsError) as exc:
        rf(value)
    assert "publication_year" in str(exc.value)
    assert value.strip() in str(exc.value) or value.strip() == ""


def test_negated_open_range_goes_to_must_not():
    # publication_year:!2021- == NOT (year >= 2021)
    out = build_vector_filter({"filters": [{"publication_year": "!2021-"}]})
    assert out == {
        "bool": {"must_not": [{"range": {"publication_year": {"gte": 2021}}}]}
    }


def test_negated_or_is_not_any_of():
    # classic: !a|b == NOT (a or b)
    out = build_vector_filter({"filters": [{"publication_year": "!2021|2022"}]})
    assert out == {
        "bool": {
            "must_not": [
                {
                    "bool": {
                        "should": [
                            {"term": {"publication_year": 2021}},
                            {"term": {"publication_year": 2022}},
                        ],
                        "minimum_should_match": 1,
                    }
                }
            ]
        }
    }


def test_full_filter_shape_for_since_year_chip():
    """The exact params the GUI 'Since 2020' chip + semantic search produce."""
    out = build_vector_filter(
        {"filters": [{"publication_year": "2020-"}, {"type": "article"}]}
    )
    assert out == {
        "bool": {
            "must": [
                {"range": {"publication_year": {"gte": 2020}}},
                {"term": {"type": "article"}},
            ]
        }
    }


def test_institution_lineage_chip_is_served_as_direct_affiliation():
    """The GUI's only institution facet is lineage; the vector index has no
    lineage field, so it maps to institution_ids (direct affiliation) rather
    than 400ing the semantic-mode Institution chip (#862)."""
    out = build_vector_filter(
        {"filters": [{"authorships.institutions.lineage": "I27837315"}]}
    )
    assert out == {
        "bool": {"must": [{"term": {"institution_ids": "https://openalex.org/I27837315"}}]}
    }
    out = build_vector_filter(
        {"filters": [{"authorships.institutions.lineage": "I27837315|i4210140016"}]}
    )
    assert out["bool"]["must"][0]["terms"]["institution_ids"] == [
        "https://openalex.org/I27837315",
        "https://openalex.org/I4210140016",
    ]


# --- Hydration re-checks the filters on works-v34 (oxjob #1433) -------------
# The vector index's filter fields go stale when a work's metadata changes
# without its text changing (the 2026-09-27 affiliation swap), so a kNN hit can
# match a filter its current record no longer does.


def test_license_translates_to_the_url_field_on_works():
    """The vector filter carries the license URL; works-v34 keeps the URL in
    primary_location.license_id (the bare slug lives in .license)."""
    out = _translate_filter_for_works(
        build_vector_filter({"filters": [{"primary_location.license": "cc-by"}]})
    )
    assert out == {
        "bool": {"must": [{"term": {
            "primary_location.license_id.keyword": "https://openalex.org/licenses/cc-by"
        }}]}
    }


def test_translation_reaches_nested_range_clauses():
    out = _translate_filter_for_works(
        build_vector_filter({"filters": [{"publication_year": "2020-|null"}, {"type": "!article"}]})
    )
    assert out == {
        "bool": {
            "must": [{"bool": {
                "should": [
                    {"range": {"publication_year": {"gte": 2020}}},
                    {"bool": {"must_not": [{"exists": {"field": "publication_year"}}]}},
                ],
                "minimum_should_match": 1,
            }}],
            "must_not": [{"term": {"type.lower": "article"}}],
        }
    }


class _FakeES:
    def __init__(self):
        self.calls = []

    def search(self, index, body):
        self.calls.append(("search", body))
        # works-v34 says only W1 still matches the filter
        return {"hits": {"hits": [{"_id": "https://openalex.org/W1", "_source": {"id": "https://openalex.org/W1"}}]}}

    def mget(self, index, body, _source_excludes):
        self.calls.append(("mget", body))
        return {"docs": [{"_id": i, "found": True, "_source": {"id": i}} for i in body["ids"]]}


def test_hydrate_drops_hits_whose_current_record_fails_the_filter(monkeypatch):
    es = _FakeES()
    monkeypatch.setattr(vector_index.connections, "get_connection", lambda alias: es)
    works_filter = _translate_filter_for_works(
        build_vector_filter({"filters": [{"authorships.institutions.lineage": "I161941770"}]})
    )
    hits = hydrate_results(
        [("https://openalex.org/W1", 0.8, 0), ("https://openalex.org/W7212882965", 0.9, 0)],
        works_filter=works_filter,
    )
    assert [h["_id"] for h in hits] == ["https://openalex.org/W1"]
    kind, body = es.calls[0]
    assert kind == "search"
    assert body["query"]["bool"]["filter"] == [
        {"ids": {"values": ["https://openalex.org/W1", "https://openalex.org/W7212882965"]}},
        {"bool": {"must": [{"term": {"authorships.institutions.id": "https://openalex.org/I161941770"}}]}},
    ]
    assert body["size"] == 2


def test_hydrate_without_filters_keeps_mget(monkeypatch):
    es = _FakeES()
    monkeypatch.setattr(vector_index.connections, "get_connection", lambda alias: es)
    hits = hydrate_results([("https://openalex.org/W1", 0.8, 0), ("https://openalex.org/W2", 0.9, 0)])
    assert [c[0] for c in es.calls] == ["mget"]
    assert [h["_id"] for h in hits] == ["https://openalex.org/W2", "https://openalex.org/W1"]


class _FakeVectorES:
    """Returns `n_hits` hits and reports a kNN pool of `pool` works."""

    def __init__(self, n_hits, pool):
        self.n_hits, self.pool, self.bodies = n_hits, pool, []

    def search(self, index, body):
        self.bodies.append(body)
        hits = [{"_id": f"https://openalex.org/W{i}", "_score": 0.9, "fields": {"cited_by_count": [1]}}
                for i in range(self.n_hits)]
        return {"hits": {"hits": hits}, "aggregations": {"pool": {"value": self.pool}}}


def test_broad_filter_runs_as_post_filter_over_the_pool(monkeypatch):
    es = _FakeVectorES(n_hits=50, pool=1000)
    monkeypatch.setattr(vector_index.connections, "get_connection", lambda alias: es)
    fd = build_vector_filter({"filters": [{"type": "article"}]})
    results, complete = vector_index.execute_vector_search([0.1] * 4, fd, k=50, num_candidates=100, post_filter_pool=1000)
    assert len(results) == 50 and complete
    body = es.bodies[0]
    assert "filter" not in body["knn"]
    assert body["knn"]["k"] == body["knn"]["num_candidates"] == 1000
    assert body["post_filter"] == fd and body["size"] == 50


def test_a_full_pool_that_keeps_too_few_is_incomplete(monkeypatch):
    es = _FakeVectorES(n_hits=7, pool=1000)
    monkeypatch.setattr(vector_index.connections, "get_connection", lambda alias: es)
    fd = build_vector_filter({"filters": [{"publication_year": "2020"}]})
    assert vector_index.execute_vector_search([0.1] * 4, fd, k=50, post_filter_pool=1000)[1] is False


def test_few_hits_are_complete_when_the_similarity_cut_emptied_the_pool(monkeypatch):
    es = _FakeVectorES(n_hits=7, pool=300)
    monkeypatch.setattr(vector_index.connections, "get_connection", lambda alias: es)
    fd = build_vector_filter({"filters": [{"publication_year": "2020"}]})
    results, complete = vector_index.execute_vector_search([0.1] * 4, fd, k=50, post_filter_pool=1000)
    assert len(results) == 7 and complete


class _PoolES:
    """Keeps `per_1000` matches per 1,000 pooled works; the pre-filter (knn.filter) returns 50."""

    def __init__(self, per_1000):
        self.per_1000, self.calls = per_1000, []

    def search(self, index, body):
        pool = body["knn"]["k"] if "post_filter" in body else None
        self.calls.append(pool or "pre")
        n = min(50, self.per_1000 * pool // 1000) if pool else 50
        hits = [{"_id": f"https://openalex.org/W{i}", "_score": 0.9} for i in range(n)]
        return {"hits": {"hits": hits}, "aggregations": {"pool": {"value": pool or 0}}}


def _run_semantic(monkeypatch, es, filters):
    monkeypatch.setattr(vector_index.connections, "get_connection", lambda alias: es)
    monkeypatch.setattr(vector_index, "embed_query", lambda text: [0.1] * 4)
    monkeypatch.setattr(vector_index, "hydrate_results", lambda results, *a, **kw: [{"_id": r[0]} for r in results])
    monkeypatch.setattr(vector_index.settings, "SEMANTIC_TEXT_BOOST", False)
    return vector_index.vector_semantic_search({"search": "q", "filters": filters, "per_page": 25}, "works", "walden")


def test_single_year_tries_the_bigger_pool_before_the_pre_filter(monkeypatch):
    es = _PoolES(per_1000=15)   # 15 in 1,000 -> 50 in 5,000
    _run_semantic(monkeypatch, es, [{"publication_year": "2025"}])
    assert es.calls == [1000, 5000]


def test_rare_filter_skips_the_bigger_pool(monkeypatch):
    es = _PoolES(per_1000=3)    # 3 in 1,000 -> 15 in 5,000: not worth it
    _run_semantic(monkeypatch, es, [{"language": "ja"}])
    assert es.calls == [1000, "pre"]


def test_id_filters_stay_pre_filtered(monkeypatch):
    assert vector_index._has_id_filter({"filters": [{"publication_year": "2020"}, {"authorships.author.id": "A1"}]})
    assert not vector_index._has_id_filter({"filters": [{"type": "article"}, {"has_abstract": "true"}]})
    es = _PoolES(per_1000=50)
    _run_semantic(monkeypatch, es, [{"authorships.author.id": "A1"}])
    assert es.calls == ["pre"]


class _CountES:
    """Answers the pre-filter's capped count with `matches`, then returns one hit."""

    def __init__(self, matches):
        self.matches, self.bodies = matches, []

    def search(self, index, body):
        self.bodies.append(body)
        if body.get("size") == 0:
            return {"hits": {"total": {"value": min(self.matches, body["track_total_hits"]), "relation": "eq"}, "hits": []}}
        return {"hits": {"hits": [{"_id": "https://openalex.org/W1", "_score": 0.8}]}}


def _pre_filter(monkeypatch, matches, exact_max, visit):
    es = _CountES(matches)
    monkeypatch.setattr(vector_index.connections, "get_connection", lambda alias: es)
    monkeypatch.setattr(vector_index.settings, "VECTOR_EXACT_MAX_MATCHES", exact_max)
    monkeypatch.setattr(vector_index.settings, "VECTOR_PREFILTER_VISIT_PERCENTAGE", visit)
    fd = build_vector_filter({"filters": [{"authorships.institutions.lineage": "I1"}, {"publication_year": "2024"}]})
    assert vector_index.execute_vector_search([0.1] * 4, fd, k=50, num_candidates=300) == [
        ("https://openalex.org/W1", 0.8, 0)]
    return es.bodies, fd


def test_unset_tuning_keeps_the_plain_pre_filtered_knn(monkeypatch):
    bodies, fd = _pre_filter(monkeypatch, matches=14_000, exact_max=0, visit=0)
    assert len(bodies) == 1 and bodies[0]["knn"]["filter"] == fd and "visit_percentage" not in bodies[0]["knn"]


def test_restrictive_filter_is_scored_exactly(monkeypatch):
    bodies, fd = _pre_filter(monkeypatch, matches=14_000, exact_max=500_000, visit=1.0)
    count, search = bodies
    assert count["query"] == {"bool": {"filter": fd}} and count["track_total_hits"] == 500_001
    assert "knn" not in search
    script_score = search["query"]["script_score"]
    assert script_score["query"] == {"bool": {"filter": fd}}
    assert script_score["min_score"] == 0.75  # (1 + 0.5) / 2: the kNN similarity floor in _score units
    assert "cosineSimilarity" in script_score["script"]["source"] and search["size"] == 50


def test_broad_pre_filter_stays_knn_with_a_visit_cap(monkeypatch):
    bodies, fd = _pre_filter(monkeypatch, matches=800_000, exact_max=500_000, visit=1.0)
    knn = bodies[1]["knn"]
    assert knn["filter"] == fd and knn["visit_percentage"] == 1.0 and knn["num_candidates"] == 300
