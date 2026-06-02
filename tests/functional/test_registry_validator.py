"""Acceptance tests for the registry-backed OQO validator (#294 Phase B).

POSITIVES are the in-scope worked examples from oxjob #284's EXAMPLES.md (Stage
A/B/L rows with status ✅/⚠️). Every one must validate against the live column
registry — they are real queries that execute today, so a strict validator must
never reject them. NEGATIVES exercise the three registry-backed checks
(invalid_column / invalid_operator_for_column / invalid_value_type) plus the
pre-existing shape checks.

Run with `pytest --noconftest` — the top-level conftest eagerly imports the app.
"""

import pytest

from query_translation.oqo import OQO
from query_translation.validator import validate_oqo


# --- In-scope #284 worked examples (must all validate) -----------------------

POSITIVES = {
    "A01": {"get_rows": "works"},
    "A02": {"get_rows": "works", "filter_rows": [
        {"column_id": "publication_year", "value": "2020"}]},
    "A03": {"get_rows": "works", "filter_rows": [
        {"join": "or", "filters": [
            {"column_id": "authorships.institutions.lineage", "value": "I33213144"},
            {"column_id": "authorships.institutions.lineage", "value": "I136199984"}]},
        {"column_id": "publication_year", "value": "2020", "operator": ">="}]},
    "A04": {"get_rows": "works", "filter_rows": [
        {"column_id": "authorships.institutions.lineage", "value": "I130438778"}],
        "sort_by_column": "cited_by_count", "sort_by_order": "desc"},
    "A05": {"get_rows": "works", "filter_rows": [
        {"column_id": "funders.id", "value": "F4320332161"},
        {"column_id": "authorships.institutions.lineage", "value": "I201448701"},
        {"column_id": "open_access.is_oa", "value": False}]},
    "A06": {"get_rows": "works", "filter_rows": [
        {"column_id": "title_and_abstract.search", "value": "climate change",
         "operator": "contains"}]},
    "A07": {"get_rows": "authors", "sort_by_column": "works_count",
            "sort_by_order": "desc"},
    "A08": {"get_rows": "authors", "filter_rows": [
        {"column_id": "last_known_institutions.country_code", "value": "BR"},
        {"column_id": "has_orcid", "value": True}]},
    "A09": {"get_rows": "authors", "filter_rows": [
        {"column_id": "ids.openalex", "value": "A5022654839"}]},
    "A10": {"get_rows": "sources", "filter_rows": [
        {"column_id": "type", "value": "journal"}]},
    "A11": {"get_rows": "institutions", "filter_rows": [
        {"column_id": "country_code", "value": "FR"}]},
    "A12": {"get_rows": "topics", "filter_rows": [
        {"column_id": "domain.id", "value": "3"}]},
    "A13": {"get_rows": "authors", "filter_rows": [
        {"column_id": "last_known_institutions.id", "value": "I114027177"},
        {"column_id": "topics.id", "value": "T10895"}]},
    "B01": {"get_rows": "works", "filter_rows": [
        {"column_id": "authorships.author.id", "value": "A5066175077"}],
        "group_by": [{"column_id": "authorships.author.id"}]},
    "B02": {"get_rows": "works", "filter_rows": [
        {"column_id": "default.search", "value": "Macrocystis pyrifera",
         "operator": "contains"}],
        "group_by": [{"column_id": "authorships.author.id"}]},
    "B03": {"get_rows": "works", "filter_rows": [
        {"column_id": "publication_year", "value": "1976", "operator": ">="}],
        "group_by": [{"column_id": "primary_topic.id"},
                     {"column_id": "publication_year"}]},
    "B04": {"get_rows": "works", "filter_rows": [
        {"column_id": "authorships.countries", "value": "col_eu27"},
        {"column_id": "authorships.countries", "value": "US"}],
        "group_by": [{"column_id": "primary_topic.id"}]},
    "B05": {"get_rows": "works", "filter_rows": [
        {"column_id": "is_retracted", "value": True}],
        "group_by": [{"column_id": "authorships.institutions.lineage"}]},
    "B06": {"get_rows": "works", "filter_rows": [
        {"column_id": "title_and_abstract.search", "value": "coral bleaching",
         "operator": "contains"},
        {"column_id": "cited_by_count", "value": "100", "operator": ">"}],
        "group_by": [{"column_id": "primary_location.source.id"}]},
    "B07": {"get_rows": "works", "filter_rows": [
        {"column_id": "type", "value": "book"}],
        "group_by": [{"column_id": "primary_topic.field.id"}]},
    "B08": {"get_rows": "works", "filter_rows": [
        {"column_id": "authorships.institutions.lineage", "value": "I154570441"},
        {"column_id": "is_retracted", "value": True}],
        "group_by": [{"column_id": "authorships.author.id"}]},
    "B09": {"get_rows": "works", "filter_rows": [
        {"column_id": "authorships.institutions.lineage", "value": "I107639228"}],
        "group_by": [{"column_id": "sustainable_development_goals.id"}]},
    "L01": {"get_rows": "works", "filter_rows": [
        {"column_id": "title_and_abstract.search", "value": "agile",
         "operator": "contains"},
        {"join": "or", "filters": [
            {"column_id": "title_and_abstract.search", "value": "supply chain",
             "operator": "contains"},
            {"column_id": "title_and_abstract.search", "value": "value chain",
             "operator": "contains"}]}]},
    "L02a": {"get_rows": "works", "filter_rows": [
        {"column_id": "title_and_abstract.search", "value": "\"smart phone\"~3",
         "operator": "contains"}]},
    "L05": {"get_rows": "works", "filter_rows": [
        {"join": "or", "filters": [
            {"column_id": "title_and_abstract.search", "value": "autism",
             "operator": "contains"},
            {"column_id": "title_and_abstract.search", "value": "ASD",
             "operator": "contains"}]},
        {"column_id": "publication_year", "value": "2015", "operator": ">="},
        {"column_id": "publication_year", "value": "2024", "operator": "<="},
        {"join": "or", "filters": [
            {"column_id": "type", "value": "article"},
            {"column_id": "type", "value": "review"}]},
        {"column_id": "language", "value": "en"}]},
    "L06": {"get_rows": "works", "filter_rows": [
        {"column_id": "open_access.oa_status", "value": "gold"},
        {"column_id": "funders.id", "value": "F4320337351"}]},
    "L07": {"get_rows": "works", "filter_rows": [
        {"column_id": "title_and_abstract.search", "value": "CRISPR genome editing",
         "operator": "contains"},
        {"column_id": "publication_year", "value": "2018", "operator": ">="},
        {"column_id": "publication_year", "value": "2023", "operator": "<="}],
        "sort_by_column": "cited_by_count", "sort_by_order": "desc", "sample": 500},
    "L08": {"get_rows": "works", "filter_rows": [
        {"column_id": "raw_affiliation_strings.search", "value": "library",
         "operator": "contains"}]},
    "L10": {"get_rows": "works", "filter_rows": [
        {"column_id": "doi", "value": "10.1021/es052595+"}]},
    "L11": {"get_rows": "works", "filter_rows": [
        {"column_id": "authorships.author.orcid", "value": "0000-0002-1838-9363"}]},
    "L13": {"get_rows": "works", "filter_rows": [
        {"join": "or", "filters": [
            {"column_id": "type", "value": "article"},
            {"column_id": "type", "value": "review"}]}]},
    "L14": {"get_rows": "works", "filter_rows": [
        {"column_id": "language", "value": "es"}]},
    "L15": {"get_rows": "works", "filter_rows": [
        {"column_id": "title_and_abstract.search", "value": "covid",
         "operator": "contains"},
        {"column_id": "title_and_abstract.search", "value": "pediatric",
         "operator": "contains", "is_negated": True}]},
    "L16": {"get_rows": "works", "filter_rows": [
        {"column_id": "title_and_abstract.search", "value": "quantum computing",
         "operator": "contains"}],
        "group_by": [{"column_id": "authorships.countries"}]},
    "L22": {"get_rows": "works", "filter_rows": [
        {"column_id": "raw_author_name.search", "value": "\"john smith\"~2",
         "operator": "contains"}]},
}


# --- Logistics layer (#318): select / seed / pagination positives ------------
POSITIVES.update({
    "P01_select": {"get_rows": "works",
                   "select": ["id", "display_name", "cited_by_count"]},
    "P02_seeded_sample": {"get_rows": "works", "sample": 100, "seed": "42"},
    "P03_per_page_page": {"get_rows": "works", "per_page": 50, "page": 2},
    "P04_per_page_bounds_lo": {"get_rows": "works", "per_page": 1, "page": 1},
    "P05_per_page_bounds_hi": {"get_rows": "works", "per_page": 200},
    "P06_cursor_only": {"get_rows": "works", "cursor": "*"},
    "P07_select_authors": {"get_rows": "authors",
                           "select": ["id", "display_name", "works_count"]},
    "P08_all_logistics": {"get_rows": "works",
                          "filter_rows": [{"column_id": "publication_year",
                                           "value": 2024, "operator": ">="}],
                          "select": ["id", "display_name"],
                          "sample": 50, "seed": 7, "per_page": 25, "page": 2},
})


@pytest.mark.parametrize("row_id", sorted(POSITIVES))
def test_in_scope_examples_validate(row_id):
    """Every in-scope #284 worked example must pass the strict validator."""
    result = validate_oqo(OQO.from_dict(POSITIVES[row_id]))
    assert result.valid, (
        f"{row_id} should validate but got: "
        f"{[(e.type, e.location) for e in result.errors]}"
    )


# --- Negative cases (must reject with the right error type) ------------------

NEGATIVES = [
    ("unknown_column",
     {"get_rows": "works", "filter_rows": [
         {"column_id": "not_a_real_column", "value": "x"}]},
     "invalid_column"),
    ("comparison_on_string",
     {"get_rows": "works", "filter_rows": [
         {"column_id": "type", "value": "article", "operator": ">"}]},
     "invalid_operator_for_column"),
    ("contains_on_number",
     {"get_rows": "works", "filter_rows": [
         {"column_id": "cited_by_count", "value": "5", "operator": "contains"}]},
     "invalid_operator_for_column"),
    ("number_on_boolean",
     {"get_rows": "works", "filter_rows": [
         {"column_id": "is_oa", "value": 5}]},
     "invalid_value_type"),
    ("nonnumeric_on_number",
     {"get_rows": "works", "filter_rows": [
         {"column_id": "cited_by_count", "value": "lots", "operator": ">"}]},
     "invalid_value_type"),
    ("contains_on_number_nested",
     {"get_rows": "works", "filter_rows": [
         {"join": "and", "filters": [
             {"column_id": "cited_by_count", "value": "5", "operator": "contains"}]}]},
     "invalid_operator_for_column"),
    ("unknown_entity",
     {"get_rows": "widgets", "filter_rows": []},
     "invalid_entity"),
    ("bad_operator_string",
     {"get_rows": "works", "filter_rows": [
         {"column_id": "type", "value": "article", "operator": "equals"}]},
     "invalid_operator"),
    ("bad_sort_order",
     {"get_rows": "works", "sort_by_column": "cited_by_count",
      "sort_by_order": "ascending"},
     "invalid_sort_order"),
    ("bad_sample",
     {"get_rows": "works", "sample": -1},
     "invalid_sample"),
    ("empty_branch",
     {"get_rows": "works", "filter_rows": [{"join": "or", "filters": []}]},
     "empty_branch"),
    ("unknown_sort_column",
     {"get_rows": "works", "sort_by_column": "bogus_col", "sort_by_order": "desc"},
     "invalid_column"),
    ("unknown_group_by_column",
     {"get_rows": "works", "group_by": [{"column_id": "bogus_col"}]},
     "invalid_column"),
    # --- logistics layer (#318) negatives ---
    ("unknown_select_column",
     {"get_rows": "works", "select": ["id", "not_a_real_field"]},
     "invalid_select_column"),
    ("page_and_cursor",
     {"get_rows": "works", "page": 2, "cursor": "*"},
     "invalid_pagination"),
    ("per_page_zero",
     {"get_rows": "works", "per_page": 0},
     "invalid_per_page"),
    ("per_page_too_big",
     {"get_rows": "works", "per_page": 9999},
     "invalid_per_page"),
    ("page_zero",
     {"get_rows": "works", "page": 0},
     "invalid_page"),
]


@pytest.mark.parametrize("desc,oqo_dict,expected_type",
                         NEGATIVES, ids=[n[0] for n in NEGATIVES])
def test_invalid_oqo_rejected(desc, oqo_dict, expected_type):
    """Each bad OQO must be rejected with the expected error type."""
    result = validate_oqo(OQO.from_dict(oqo_dict))
    assert not result.valid, f"{desc} should be invalid"
    assert expected_type in {e.type for e in result.errors}, (
        f"{desc}: expected {expected_type}, got "
        f"{[e.type for e in result.errors]}"
    )


# --- Logistics layer (#318): error locations + non-blocking warning ----------

def test_invalid_select_column_has_indexed_location():
    """The bad select entry is pinpointed at `select[i]` (the 2nd here)."""
    result = validate_oqo(OQO.from_dict(
        {"get_rows": "works", "select": ["id", "bogus_field"]}
    ))
    assert not result.valid
    locs = {e.location for e in result.errors if e.type == "invalid_select_column"}
    assert "select[1]" in locs, locs


def test_seed_without_sample_is_a_nonblocking_warning():
    """`seed` without `sample` is inert — a warning, not an error."""
    result = validate_oqo(OQO.from_dict({"get_rows": "works", "seed": "42"}))
    assert result.valid, [(e.type, e.location) for e in result.errors]
    assert "seed_without_sample" in {w.type for w in result.warnings}


# --- Property catalog <-> executor coverage (#334) ---------------------------
# The #334 bug: an entity can be in the property catalog (so the validator accepts
# it) yet missing a branch in `_resolve_entity` (so `/query` 400s `invalid_entity`
# at execution). That split is exactly what let `/locations` validate but never
# execute. Guard the invariant: every catalog entity must also resolve.

from core.properties import ENTITY_PROPERTIES
from query_translation.views import _resolve_entity
from core.exceptions import APIQueryParamsError


@pytest.mark.parametrize(
    "entity", sorted(ENTITY_PROPERTIES), ids=sorted(ENTITY_PROPERTIES)
)
def test_every_registry_entity_resolves_for_execution(entity):
    """If the validator accepts an entity, `_resolve_entity` must execute it."""
    try:
        fields_dict, index_name, default_sort, _schema = _resolve_entity(
            entity, connection="walden"
        )
    except APIQueryParamsError:
        pytest.fail(
            f"'{entity}' is in ENTITY_PROPERTIES (validator accepts it) but "
            f"_resolve_entity raised — it would 400 invalid_entity at /query."
        )
    assert fields_dict and index_name and default_sort


def test_locations_resolves_to_its_walden_index():
    """#334 regression: locations resolves to locations-v1 with its own sort."""
    _fields, index_name, default_sort, _schema = _resolve_entity(
        "locations", connection="walden"
    )
    assert index_name == "locations-v1"
    assert default_sort == ["work_id", "native_id"]
