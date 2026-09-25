"""works `study_designs.id` filter/group_by plumbing (oxjob #1312). No ES, no app.

ES holds the full id (`https://openalex.org/study-designs/<slug>`) on the house
keyword + `.lower` mapping; the filter must accept the bare slug the GUI sends,
the short id and the full id, and group_by must name the buckets without an
index lookup (the slug id can't route through `get_id_display_names`).

    PYTHONPATH=. venv/bin/python -m pytest tests/unit/test_study_designs.py --noconftest -q
"""

import pytest

from core.fields import (
    ENTITY_ID_PARAM_TYPES,
    ID_PATH_SEGMENT_BY_ENTITY_TYPE,
    TermField,
    _canonicalize_entity_ids,
)
from core.group_by.display_names import get_display_name_mapping
from core.group_by.filter import filter_group_by
from core.group_by.results import format_key

FULL = "https://openalex.org/study-designs/meta-analysis"
ES_FIELD = "study_designs.id.lower"

SLUGS = {
    "randomized-controlled-trial": "Randomized Controlled Trial",
    "clinical-trial": "Clinical Trial",
    "observational-study": "Observational Study",
    "case-report": "Case Report",
    "systematic-review": "Systematic Review",
    "meta-analysis": "Meta-Analysis",
    "study-protocol": "Study Protocol",
}


def _query(value):
    f = TermField(param="study_designs.id")
    f.value = value
    return f.build_query().to_dict()


@pytest.mark.parametrize(
    "value", ["meta-analysis", "study-designs/meta-analysis", FULL, "Meta-Analysis"]
)
def test_every_id_form_filters_on_the_full_url(value):
    assert _query(value) == {"term": {ES_FIELD: FULL}}


@pytest.mark.parametrize("value", ["meta-analysis", "study-designs/meta-analysis", FULL])
def test_negation_every_form(value):
    assert _query("!" + value) == {"bool": {"must_not": [{"term": {ES_FIELD: FULL}}]}}


def test_null_and_not_null_are_existence_checks():
    assert _query("null") == {"bool": {"must_not": [{"exists": {"field": "study_designs.id.lower"}}]}}
    assert _query("!null") == {"exists": {"field": "study_designs.id.lower"}}


def test_or_values_expand_to_full_urls():
    f = TermField(param="study_designs.id")
    q = f.build_terms_query(["meta-analysis", "study-designs/case-report", FULL]).to_dict()
    assert q == {
        "terms": {
            ES_FIELD: [
                FULL,
                "https://openalex.org/study-designs/case-report",
                FULL,
            ]
        }
    }


def test_entity_maps():
    assert ENTITY_ID_PARAM_TYPES["study_designs.id"] == "study-designs"
    assert ID_PATH_SEGMENT_BY_ENTITY_TYPE["study-designs"] == "study-designs"
    # collection members (short ids from users-api) become the indexed full URL
    assert _canonicalize_entity_ids(["meta-analysis"], "study-designs") == [FULL]


def test_group_by_display_names_come_from_the_closed_vocab():
    keys = [f"https://openalex.org/study-designs/{s}" for s in SLUGS] + ["unknown"]
    names = get_display_name_mapping(keys, "study_designs.id")
    assert names == {f"https://openalex.org/study-designs/{s}": n for s, n in SLUGS.items()}


def test_group_by_key_is_left_as_the_full_url():
    assert format_key(FULL, "study_designs.id", "works-v34") == FULL


def test_group_by_q_is_applied_after_naming_not_as_a_prefix_query():
    sentinel = object()
    assert filter_group_by(TermField(param="study_designs.id"), "study_designs.id", "meta", sentinel) is sentinel


def test_works_schema_dumps_study_designs():
    from works.schemas import WorksSchema

    rows = [{"id": FULL, "display_name": "Meta-Analysis"}]
    assert WorksSchema(only=("study_designs",)).dump({"study_designs": rows}) == {"study_designs": rows}
    # absent in the doc (no design, or before the walden fill) -> []
    assert WorksSchema(only=("study_designs",)).dump({}) == {"study_designs": []}
