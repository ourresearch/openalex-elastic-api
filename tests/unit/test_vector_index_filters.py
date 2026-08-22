"""Range-filter grammar on the semantic (vector) pre-filter path — oxjob #862.

The GUI Year chip emits open-ended ranges (``publication_year:2025-``), and the
OQL renderer emits ``N-`` / ``-N`` for ``>=`` / ``<=``. These used to raise a
ValueError inside ``_build_range_filter`` → unhandled → HTML 500 on
``search.semantic`` requests. The vector path must speak the same grammar as
the classic ``RangeField``.
"""
import pytest

from core.exceptions import APIQueryParamsError
from core.vector_index import _build_range_filter, build_vector_filter


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
