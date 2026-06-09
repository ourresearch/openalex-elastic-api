"""Entity registry — the single source of entity-level facts (oxjob #405).

`core/entities.py` projects every `config/<entity>.yaml` into an `EntityType`.
It started (#363) as just the OQL Tier-2 ID *shape*; #405 widened it to carry the
curated entity-level facts (display names, description, closed-vocab `values`, the
authored `isNative` flag, `alternate_names`) so the `/meta` catalog and `/entities`
route read THE registry instead of each keeping a copy of the config dict.

These tests pin the projection and guard the two "native" notions that legitimately
diverge (`is_native` authored vs `is_native_id` derived). Tier-2 shape behaviour
itself lives in `test_value_domain.py`; this file owns the curated-field contract.

Pure: no app boot, no query_translation stub (core.entities only reads the yaml).
    PYTHONPATH=. pytest tests/oql/test_entity_registry.py -q --noconftest
"""
import pytest

from core.entities import (  # noqa: E402
    EntityType,
    get_entity_type,
    native_id_entities,
    _registry,
)

# The 22 entity types shipped in config/*.yaml (one file each).
ALL_ENTITIES = sorted(_registry().keys())

# Entities whose `values:` is a non-empty closed vocabulary (the renderer's
# Tier-1 set + the three currently-unread lists). Native-ID entities carry a
# null/empty `values` and must project to None.
CLOSED_VOCAB = {
    "continents", "countries", "domains", "fields", "institution-types",
    "languages", "licenses", "oa-statuses", "sdgs", "source-types",
    "subfields", "work-types",
}


def test_all_22_entities_present():
    assert len(ALL_ENTITIES) == 22, ALL_ENTITIES


@pytest.mark.parametrize("name", ALL_ENTITIES)
def test_every_entity_exposes_curated_fields(name):
    """Each entity resolves its curated facts from the registry — display name
    (plural + singular), a description, and the authored native flag."""
    e = get_entity_type(name)
    assert isinstance(e, EntityType) and e.name == name
    assert e.display_name, f"{name}: missing displayName"
    assert e.display_name_singular, f"{name}: missing displayNameSingular"
    assert e.description, f"{name}: missing descr/descrFull"
    assert isinstance(e.is_native, bool), f"{name}: isNative must be a bool"
    assert isinstance(e.alternate_names, tuple), f"{name}: alternate_names is a tuple"


@pytest.mark.parametrize("name", ALL_ENTITIES)
def test_values_is_list_for_closed_vocab_else_none(name):
    """`values` projects to a non-empty list of {id, display_name} for a closed
    vocabulary, and to None for an open/native entity (no empty-list ambiguity)."""
    e = get_entity_type(name)
    if name in CLOSED_VOCAB:
        assert isinstance(e.values, list) and e.values, f"{name}: expected closed vocab"
        first = e.values[0]
        assert "id" in first and "display_name" in first, first
    else:
        assert e.values is None, f"{name}: open entity must have values=None, got {e.values!r}"


def test_native_flag_distinguishes_authored_from_derived():
    """`is_native` (authored GUI flag) and `is_native_id` (derived ID shape) are
    deliberately separate: continents is a closed vocab (authored False) yet its
    ids are Q-prefixed, so it is native-*shaped* (derived True). #363's Tier-2
    logic depends on the derived one — this guards against collapsing them."""
    c = get_entity_type("continents")
    assert c.is_native is False
    assert c.is_native_id is True


def test_native_id_set_is_derived_from_idregex():
    """The Tier-2 set comes from single-letter idRegex prefixes, unchanged by
    #405 (works/authors/… plus continents' Q)."""
    native = set(native_id_entities())
    assert native == {
        "authors", "awards", "concepts", "continents", "funders",
        "institutions", "publishers", "sources", "topics", "works",
    }, native


def test_unknown_entity_returns_none():
    assert get_entity_type("not-an-entity") is None
    assert get_entity_type(None) is None
    assert get_entity_type("") is None
