"""Capability-parity gate for the unified per-property capability catalog (#450).

#450 collapses four drifted vocabularies — filter / sort / group_by were gated on
`ENTITY_PROPERTIES` membership, while `column`/`select` was gated against a SEPARATE
namespace (the marshmallow MessageSchema, `get_selectable_fields`) — into ONE catalog:
each Property's `actions` (baked at boot by `_derive_actions`), read by the OQO
validator for every clause AND published verbatim on `/properties` (v3-line, #450
public surfacing).

The capabilities are **API-actual** (Jason's rule: "OQL never rejects what a raw URL
would allow" — and never *claims* what the raw URL can't do):

  * sort     — every filter-capable column. core/sort.py resolves any registry field,
               but sorting a search column or the `collection` transport 500s in ES
               (live-probed 2026-06-12), so capability follows the `filter` action.
  * group_by — the filter-capable columns the live single-dim rule accepts. Derived
               from `core.validate.group_by_rejection` — the SAME function
               `validate_group_by` enforces at request time, so catalog and
               enforcement cannot drift (these tests re-verify it anyway).
  * column   — exactly the result-schema selectable set (`get_selectable_fields`,
               the `?select=` vocabulary).

This DELIBERATELY TIGHTENED the pre-#450 OQO validator (loose membership accepted
e.g. `group by doi` / `sort by abstract.search`, which the live API rejects/500s).
The pre-tightening baseline lives in this file's git history; the counts below are
the API-actual baseline. If a future change moves a capability again, update
PARITY_BASELINE in the SAME commit and call it out — never silently.

Run with `pytest --noconftest` (the top-level conftest eagerly imports the app).
"""

import importlib

import pytest

from core.properties import (
    CAP_COLUMN,
    CAP_FILTER,
    CAP_GROUP_BY,
    CAP_SORT,
    ENTITY_FIELDS_MODULES,
    ENTITY_PROPERTIES,
    get_entity_capabilities,
    get_entity_columns,
    get_selectable_fields,
)
from core.validate import group_by_rejection
from query_translation.oqo import OQO, GroupBy, SortBy
from query_translation.validator import validate_oqo

# API-actual accept-counts (#450 public surfacing): (sortable, groupable, columnar)
# per entity, counted over the capability catalog's full key set (registry columns —
# aliases included — ∪ selectable result fields). sort == the filter-capable count;
# group_by == the live `validate_group_by` subset of it; column == |selectable|.
PARITY_BASELINE = {
    "works": (190, 164, 58),
    "authors": (39, 34, 21),
    "sources": (44, 31, 43),
    "institutions": (30, 27, 31),
    "funders": (22, 19, 18),
    "publishers": (21, 18, 20),
    "topics": (11, 8, 15),
    "keywords": (6, 3, 8),
    "concepts": (15, 12, 19),
}

ENTITIES = list(PARITY_BASELINE)


def _live_fields_dict(entity):
    """The engine `Field` objects the live request path executes — the ground
    truth the derived capabilities must reproduce."""
    mod = importlib.import_module(ENTITY_FIELDS_MODULES[entity])
    fields_dict = getattr(mod, "fields_dict", None)
    if fields_dict is None:
        fields_dict = {f.param: f for f in getattr(mod, "fields", [])}
    return fields_dict


def _accepts(oqo, location_prefix):
    """True iff validate_oqo raises no error targeting the given clause."""
    errors = validate_oqo(oqo).errors
    return not [e for e in errors if (e.location or "").startswith(location_prefix)]


@pytest.mark.parametrize("entity", ENTITIES)
def test_capabilities_match_live_engine_rules(entity):
    """The baked capability sets equal the LIVE engine rules, recomputed here from
    the engine Field objects — the API-actual lock."""
    caps = get_entity_capabilities(entity)
    assert caps is not None
    fields_dict = _live_fields_dict(entity)

    sortable = {name for name, a in caps.items() if CAP_SORT in a}
    groupable = {name for name, a in caps.items() if CAP_GROUP_BY in a}
    columnar = {name for name, a in caps.items() if CAP_COLUMN in a}

    # sort == the filter-capable columns (search/collection columns 500 on sort).
    expected_sortable = {
        name for name, f in fields_dict.items() if CAP_FILTER in f.actions
    }
    assert sortable == expected_sortable

    # group_by == sortable minus what the live single-dim rule rejects.
    expected_groupable = {
        name for name in expected_sortable
        if group_by_rejection(fields_dict[name]) is None
    }
    assert groupable == expected_groupable

    # column == exactly the result-schema selectable set.
    assert columnar == (get_selectable_fields(entity) or set())
    assert get_entity_columns(entity) == (get_selectable_fields(entity) or set())


@pytest.mark.parametrize("entity", ENTITIES)
def test_validator_accept_counts_match_baseline(entity):
    """End-to-end: validate_oqo accept-counts over the full capability key set
    match the frozen API-actual baseline."""
    cols = sorted(get_entity_capabilities(entity))
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


def test_group_by_capability_agrees_with_request_time_validator():
    """For EVERY works column, the baked group_by capability == what the live
    `validate_group_by` would decide for a plain (cursorless) request — the
    derivation and the request-time enforcement share `group_by_rejection`, and
    this re-verifies they agree end to end."""
    from core.exceptions import APIQueryParamsError
    from core.validate import validate_group_by

    caps = get_entity_capabilities("works")
    for name, field in _live_fields_dict("works").items():
        if CAP_FILTER not in field.actions:
            continue  # search/collection: no group capability, live rule untested
        try:
            validate_group_by(field, {})
            live_ok = True
        except APIQueryParamsError:
            live_ok = False
        assert (CAP_GROUP_BY in caps[name]) == live_ok, name


def test_validator_rejects_live_rejected_group_keys():
    """Spot locks for the deliberate tightening: keys the live API rejects are now
    invalid_column in the OQO validator too (pre-#450 the loose membership rule
    accepted all of these)."""
    for bad in ("doi", "publication_date", "abstract.search", "display_name"):
        oqo = OQO(get_rows="works", group_by=[GroupBy(column_id=bad)])
        assert not _accepts(oqo, "group_by"), bad
    for good in ("type", "publication_year", "authorships.institutions.lineage"):
        oqo = OQO(get_rows="works", group_by=[GroupBy(column_id=good)])
        assert _accepts(oqo, "group_by"), good


def test_validator_rejects_es_500_sort_keys():
    """Sort keys that 500 on the live API (search columns, the collection
    transport) are now rejected up front."""
    for bad in ("abstract.search", "fulltext.search", "collection"):
        oqo = OQO(get_rows="works", sort_by=[SortBy(column_id=bad)])
        assert not _accepts(oqo, "sort_by"), bad
    for good in ("cited_by_count", "publication_date", "is_retracted"):
        oqo = OQO(get_rows="works", sort_by=[SortBy(column_id=good)])
        assert _accepts(oqo, "sort_by"), good


def test_alias_columns_keep_their_canonical_capabilities():
    """#446 demoted alias spellings from the PUBLIC catalog, but they stay live,
    resolvable columns — a raw-URL-accepted alias sort/group key must not reject."""
    caps = get_entity_capabilities("works")
    fields_dict = _live_fields_dict("works")
    aliased = [
        name for name, prop in ENTITY_PROPERTIES["works"].items()
        if prop.alternate_of and CAP_FILTER in fields_dict[name].actions
    ]
    assert aliased, "expected filter-capable #446 alias columns on works"
    for name in aliased:
        assert CAP_SORT in caps[name], name


def test_column_only_fields_are_column_capable_not_sortable():
    """Selectable-only nested result fields (open_access, authorships, id) are
    `column`-capable but NOT filter/sort/group_by — the exact split #450 unifies."""
    caps = get_entity_capabilities("works")
    for name in ("open_access", "authorships", "id"):
        assert name in caps, name
        assert caps[name] == frozenset({CAP_COLUMN}), (name, caps[name])


def test_non_returnable_predicates_are_not_column_capable():
    """A filter predicate that isn't a result field is NOT column-capable, even
    though it's sortable/groupable (`has_doi`); a search column carries only
    `search` — no sort (500s), no group (live-rejected), no column."""
    caps = get_entity_capabilities("works")
    assert CAP_COLUMN not in caps["has_doi"]
    assert CAP_SORT in caps["has_doi"] and CAP_GROUP_BY in caps["has_doi"]
    assert caps["abstract.search"] == frozenset({"search"})


def test_public_payload_actions_use_the_capability_vocabulary():
    """The serialized /properties payload speaks {filter, search, sort, group_by,
    column} — `select` is gone (renamed v3-line, #450)."""
    from core.properties import _merged_properties

    seen = set()
    for entity in ENTITIES:
        for prop in _merged_properties(entity).values():
            seen.update(prop.serialize()["actions"])
    assert "select" not in seen
    assert {"filter", "search", CAP_SORT, CAP_GROUP_BY, CAP_COLUMN} <= seen


def test_unknown_entity_has_no_capabilities():
    assert get_entity_capabilities("not-an-entity") is None
    assert get_entity_columns("not-an-entity") is None
