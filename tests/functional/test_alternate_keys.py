"""Tests for the identity realignment / alternate_keys mechanism (#446).

Each property identity gets ONE canonical key plus `alternate_keys` — alias
machine-key spellings the API keeps accepting but the PUBLIC `/properties`
catalog (and UI clients enumerating it) ignore. The invariants under test:

  * an alias param is DROPPED from the public catalog (`_canonical_catalog`);
  * its canonical property carries the alias under sorted `alternate_keys`;
  * the alias REMAINS in `ENTITY_PROPERTIES` and `works.fields.fields_dict`, so
    the filter API / OQO validator / OQL technical-column parse keep resolving it
    (demoted, NOT deprecated);
  * `serialize()` exposes `alternate_keys` but never the server-internal
    `alternate_of`;
  * the catalog builder's fold is robust to a misconfigured `alternate_of`.

No ES needed — the catalog builds at boot from the live Field objects.
"""

from dataclasses import replace

import core.properties as cp
from core.fields import Property
from works.fields import fields_dict as works_fields_dict


# The works curation signed off by Jason 2026-06-11 + the all-entity extension
# signed off 2026-06-12 (oxjobs #446 EXPLORE.md "Thread C").
# canonical param -> the alias params that fold into it.
WORKS_MERGES = {
    "authorships.author.id": ["author.id"],
    "authorships.author.orcid": ["author.orcid"],
    "authorships.institutions.id": ["institution.id", "institutions.id"],
    "authorships.institutions.country_code": ["institutions.country_code"],
    "authorships.institutions.continent": ["institutions.continent"],
    "authorships.institutions.is_global_south": ["institutions.is_global_south"],
    "authorships.institutions.ror": ["institutions.ror"],
    "authorships.institutions.type": ["institutions.type"],
    "authorships.is_corresponding": ["is_corresponding"],
    "open_access.is_oa": ["is_oa"],
    "open_access.oa_status": ["oa_status"],
    "ids.openalex": ["openalex", "openalex_id"],
    "ids.mag": ["mag"],
    "ids.pmid": ["pmid"],
    "ids.pmcid": ["pmcid"],
    "concepts.id": ["concept.id"],
    "locations.version": ["version"],
    "referenced_works": ["cites"],
    "primary_location.source.id": ["journal"],
    "best_oa_location.license": ["best_oa_location.license_id"],
    "locations.license": ["locations.license_id"],
    "primary_location.license": ["primary_location.license_id"],
    "locations.source.host_organization_lineage": [
        "locations.source.host_institution_lineage",
        "locations.source.publisher_lineage",
    ],
    "primary_location.source.host_organization_lineage": [
        "primary_location.source.host_institution_lineage",
        "primary_location.source.publisher_lineage",
    ],
    "display_name.search": ["title.search"],
    "display_name.search.exact": ["title.search.exact"],
}

ALL_ALIASES = [a for aliases in WORKS_MERGES.values() for a in aliases]

# The other 7 entities that carried duplicate alias spellings (Thread C).
# `id` is special: its FILTER role is demoted to an alternate_key of `ids.openalex`,
# but `id` remains in the public catalog as a SELECT-only column (returnable in OQL),
# so it is asserted differently (no filter action) than the fully-removed aliases.
OTHER_ENTITY_MERGES = {
    "authors": {
        "ids.openalex": ["id", "openalex", "openalex_id"],
        "x_concepts.id": ["concept.id", "concepts.id"],
    },
    "institutions": {
        "ids.openalex": ["id", "openalex", "openalex_id"],
        "x_concepts.id": ["concept.id", "concepts.id"],
    },
    "sources": {
        "ids.openalex": ["openalex", "openalex_id"],
        "x_concepts.id": ["concept.id", "concepts.id"],
    },
    "publishers": {
        "ids.openalex": ["openalex", "openalex_id"],
        "ids.ror": ["ror"],
        "ids.wikidata": ["wikidata"],
    },
    "funders": {
        "ids.openalex": ["openalex", "openalex_id"],
        "ids.ror": ["ror"],
        "ids.wikidata": ["wikidata"],
    },
    "topics": {
        "ids.openalex": ["id", "openalex"],
    },
    "concepts": {
        "ids.openalex": ["openalex", "openalex_id"],
    },
}

# Aliases that survive in the public catalog as a non-filter (select) column.
SELECT_SURVIVOR_ALIASES = {("authors", "id"), ("institutions", "id"), ("topics", "id")}


def test_aliases_dropped_from_public_catalog():
    works = cp._canonical_catalog()["works"]
    for alias in ALL_ALIASES:
        assert alias not in works, f"{alias} should be demoted from /properties"


def test_canonical_carries_sorted_alternate_keys():
    works = cp._canonical_catalog()["works"]
    for canonical, aliases in WORKS_MERGES.items():
        assert canonical in works, f"canonical {canonical} missing from catalog"
        assert works[canonical]["alternate_keys"] == sorted(aliases)


def test_aliases_still_resolve_internally():
    """Demoted, not deprecated: the alias must stay a live column everywhere the
    server resolves a filter (ENTITY_PROPERTIES) so validator/parse keep working."""
    ep = cp.ENTITY_PROPERTIES["works"]
    for alias in ALL_ALIASES:
        assert alias in ep, f"{alias} must remain resolvable in ENTITY_PROPERTIES"
        assert ep[alias].alternate_of is not None


def test_aliases_still_resolve_in_filter_layer():
    """The legacy filter API resolves via `fields_dict`, which stays 1:1."""
    for alias in ALL_ALIASES:
        assert alias in works_fields_dict
        assert works_fields_dict[alias].alternate_of is not None


def test_public_count_drops_by_exactly_the_demoted_aliases():
    works = cp._canonical_catalog()["works"]
    # 30 alias params demoted on works (the original 20 + 10 leftovers from Thread C);
    # 240 -> 210. None of the works aliases are select-only survivors.
    assert len(ALL_ALIASES) == 30
    assert len(works) == 210


def test_other_entity_canonicals_carry_alternate_keys():
    cat = cp._canonical_catalog()
    for entity, merges in OTHER_ENTITY_MERGES.items():
        ecat = cat[entity]
        for canonical, aliases in merges.items():
            assert canonical in ecat, f"{entity}: canonical {canonical} missing"
            assert ecat[canonical]["alternate_keys"] == sorted(aliases), (
                f"{entity}.{canonical} alternate_keys mismatch"
            )


def test_other_entity_aliases_demoted_from_filter_catalog():
    """Fully-removed aliases leave the public catalog; the `id` select-survivors
    stay but lose their `filter` action."""
    cat = cp._canonical_catalog()
    for entity, merges in OTHER_ENTITY_MERGES.items():
        ecat = cat[entity]
        for aliases in merges.values():
            for alias in aliases:
                if (entity, alias) in SELECT_SURVIVOR_ALIASES:
                    assert "filter" not in (ecat[alias].get("actions") or []), (
                        f"{entity}.{alias} should no longer be a filter property"
                    )
                else:
                    assert alias not in ecat, (
                        f"{entity}.{alias} should be demoted from /properties"
                    )


def test_other_entity_aliases_still_resolve_internally():
    """Demoted, not deprecated — every alias stays in ENTITY_PROPERTIES with its
    back-pointer, so the filter API / OQO validator / OQL parse keep resolving it."""
    for entity, merges in OTHER_ENTITY_MERGES.items():
        ep = cp.ENTITY_PROPERTIES[entity]
        for aliases in merges.values():
            for alias in aliases:
                assert alias in ep, f"{entity}.{alias} must stay resolvable"
                assert ep[alias].alternate_of is not None


def test_serialize_exposes_alternate_keys_not_alternate_of():
    p = Property(
        name="open_access.is_oa", type="boolean", operators=["eq"], actions=["filter"],
        alternate_keys=["is_oa"],
    )
    out = p.serialize()
    assert out["alternate_keys"] == ["is_oa"]
    assert "alternate_of" not in out


def test_serialize_sorts_alternate_keys():
    p = Property(
        name="authorships.institutions.id", type="object", operators=["eq"],
        actions=["filter"], alternate_keys=["institutions.id", "institution.id"],
    )
    assert p.serialize()["alternate_keys"] == ["institution.id", "institutions.id"]


def test_fold_inverts_alternate_of_onto_canonical():
    out = {
        "open_access.is_oa": Property("open_access.is_oa", "boolean", ["eq"], ["filter"]),
        "is_oa": Property("is_oa", "boolean", ["eq"], ["filter"],
                          alternate_of="open_access.is_oa"),
    }
    folded = cp._fold_alternate_keys(out, "works")
    assert folded["open_access.is_oa"].alternate_keys == ["is_oa"]
    # alias kept in the dict (still resolvable), still carrying its back-pointer
    assert "is_oa" in folded
    assert folded["is_oa"].alternate_of == "open_access.is_oa"


def test_fold_tolerates_missing_canonical(capsys):
    """A misconfigured alternate_of (canonical absent) must not drop the alias or
    raise — fail loud (warn) and leave the alias resolvable."""
    out = {
        "is_oa": Property("is_oa", "boolean", ["eq"], ["filter"],
                          alternate_of="nonexistent.canonical"),
    }
    folded = cp._fold_alternate_keys(out, "works")
    assert "is_oa" in folded  # not swallowed
    assert "WARNING" in capsys.readouterr().out
