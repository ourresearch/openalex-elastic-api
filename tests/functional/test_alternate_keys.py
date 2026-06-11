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


# The works curation signed off by Jason 2026-06-11 (oxjobs #446 EXPLORE.md).
# canonical param -> the alias params that fold into it.
WORKS_MERGES = {
    "authorships.author.id": ["author.id"],
    "authorships.author.orcid": ["author.orcid"],
    "authorships.institutions.id": ["institution.id", "institutions.id"],
    "authorships.institutions.country_code": ["institutions.country_code"],
    "authorships.institutions.ror": ["institutions.ror"],
    "authorships.institutions.type": ["institutions.type"],
    "authorships.is_corresponding": ["is_corresponding"],
    "open_access.is_oa": ["is_oa"],
    "open_access.oa_status": ["oa_status"],
    "ids.openalex": ["openalex_id"],
    "ids.mag": ["mag"],
    "ids.pmid": ["pmid"],
    "ids.pmcid": ["pmcid"],
    "concepts.id": ["concept.id"],
    "locations.version": ["version"],
    "referenced_works": ["cites"],
    "primary_location.source.id": ["journal"],
    "display_name.search": ["title.search"],
    "display_name.search.exact": ["title.search.exact"],
}

ALL_ALIASES = [a for aliases in WORKS_MERGES.values() for a in aliases]


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
    # 20 alias params across 19 identities are demoted; 240 -> 220.
    assert len(ALL_ALIASES) == 20
    assert len(works) == 220


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
