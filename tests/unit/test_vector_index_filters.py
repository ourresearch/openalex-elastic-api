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
