"""Capability-parity gate for the unified per-property capability catalog (#450).

#450 collapses four drifted vocabularies — filter / sort / group_by were gated on
`ENTITY_PROPERTIES` membership, while `column`/`select` was gated against a SEPARATE
namespace (the marshmallow MessageSchema, `get_selectable_fields`) — into ONE catalog,
`core.properties.get_entity_capabilities`, that the OQO validator reads for every clause.

That collapse must be **behavior-preserving**: the OQO validator's accept/reject verdict
for `sort by X` / `group by X` / `return X` (select) on every column must be byte-for-byte
what it was before #450. These tests assert exactly that, two ways:

  1. the capability catalog reproduces the pre-#450 source sets
     (sort/group_by == filter-registry membership; column == get_selectable_fields), and
  2. end-to-end `validate_oqo` accept-counts match a frozen baseline captured from the
     pre-#450 validator (the empirical ground truth in PARITY_BASELINE below).

If a future change deliberately makes a capability a meaningful subset (e.g. tightening
`group_by` to drop high-cardinality columns), update PARITY_BASELINE in the SAME commit
and call it out — never silently.

Run with `pytest --noconftest` (the top-level conftest eagerly imports the app).
"""

import pytest

from core.properties import (
    CAP_COLUMN,
    CAP_GROUP_BY,
    CAP_SORT,
    ENTITY_PROPERTIES,
    get_entity_capabilities,
    get_entity_columns,
    get_selectable_fields,
    _merged_properties,
)
from query_translation.oqo import OQO, GroupBy, SortBy
from query_translation.validator import validate_oqo

# Accept-counts captured from the validator BEFORE #450 (the loose membership rules):
# (sortable, groupable, columnar) per entity. sort==group because both were a bare
# `column_id in ENTITY_PROPERTIES` check; column == |get_selectable_fields|.
#
# Updated for #446 all-entity identity realignment (sort/group counts only): demoting
# duplicate alias spellings to `alternate_keys` removes them from the public catalog
# (`_merged_properties`, which this test iterates), so fewer columns are counted. The
# aliases STILL validate when queried directly (they remain in ENTITY_PROPERTIES — the
# sibling test_capability_catalog_matches_legacy_sources and test_alternate_keys assert
# this); the count simply reflects the smaller public surface. `columnar` is unchanged
# because the demoted spellings were never selectable result fields (a bare `id` keeps
# its `select` capability — only its filter/sort/group role folds into ids.openalex).
# sort/group deltas = exactly the demoted filter spellings per entity (works −10,
# authors/sources/institutions/funders/publishers −4, concepts −2, topics −1).
PARITY_BASELINE = {
    "works": (177, 177, 58),
    "authors": (38, 38, 21),
    "sources": (43, 43, 43),
    "institutions": (29, 29, 31),
    "funders": (22, 22, 18),
    "publishers": (20, 20, 20),
    "topics": (15, 15, 15),
    "keywords": (9, 9, 8),
    "concepts": (16, 16, 19),
}

ENTITIES = list(PARITY_BASELINE)


def _accepts(oqo, location_prefix):
    """True iff validate_oqo raises no error targeting the given clause."""
    errors = validate_oqo(oqo).errors
    return not [e for e in errors if (e.location or "").startswith(location_prefix)]


@pytest.mark.parametrize("entity", ENTITIES)
def test_capability_catalog_matches_legacy_sources(entity):
    """The unified catalog's per-capability sets equal the pre-#450 source sets."""
    caps = get_entity_capabilities(entity)
    assert caps is not None

    sortable = {name for name, a in caps.items() if CAP_SORT in a}
    groupable = {name for name, a in caps.items() if CAP_GROUP_BY in a}
    columnar = {name for name, a in caps.items() if CAP_COLUMN in a}

    # sort & group_by were exactly "is a filter-registry column".
    registry_cols = set(ENTITY_PROPERTIES.get(entity, {}))
    assert sortable == registry_cols
    assert groupable == registry_cols

    # column was exactly the result-schema selectable set.
    assert columnar == (get_selectable_fields(entity) or set())
    # …and get_entity_columns is that same set (the validator's column gate).
    assert get_entity_columns(entity) == (get_selectable_fields(entity) or set())


@pytest.mark.parametrize("entity", ENTITIES)
def test_validator_accept_counts_unchanged(entity):
    """End-to-end: validate_oqo accept-counts match the frozen pre-#450 baseline."""
    cols = sorted(_merged_properties(entity))
    sortable = sum(
        _accepts(OQO(get_rows=entity, sort_by=[SortBy(column_id=c)]), "sort_by")
        for c in cols
    )
    groupable = sum(
        _accepts(OQO(get_rows=entity, group_by=[GroupBy(column_id=c)]), "group_by")
        for c in cols
    )
    columnar = sum(
        _accepts(OQO(get_rows=entity, select=[c]), "select") for c in cols
    )
    assert (sortable, groupable, columnar) == PARITY_BASELINE[entity]


def test_column_only_fields_are_column_capable_not_sortable():
    """Selectable-only nested result fields (open_access, authorships, id) are
    `column`-capable but NOT filter/sort/group_by — the exact split #450 unifies."""
    caps = get_entity_capabilities("works")
    for name in ("open_access", "authorships", "id"):
        assert name in caps, name
        assert caps[name] == frozenset({CAP_COLUMN}), (name, caps[name])


def test_non_returnable_predicates_are_not_column_capable():
    """A predicate/search column that isn't a result field is NOT column-capable,
    even though it's sort/group_by-able — the exact filter-vs-column split #450 unifies.
    (`has_doi` is a boolean filter predicate; `abstract.search` is a search field — both
    answer questions about a work without being a returnable field.)"""
    caps = get_entity_capabilities("works")
    for name in ("has_doi", "abstract.search"):
        assert name in caps, name
        assert CAP_COLUMN not in caps[name], (name, sorted(caps[name]))
        assert CAP_SORT in caps[name] and CAP_GROUP_BY in caps[name], name


def test_unknown_entity_has_no_capabilities():
    assert get_entity_capabilities("not-an-entity") is None
    assert get_entity_columns("not-an-entity") is None
