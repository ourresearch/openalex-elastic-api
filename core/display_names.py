"""Canonical human display names + input aliases for properties (#381).

Single source of truth for the *word* a property is shown/typed as. Today that
word is hand-maintained across ≥4 drifting surfaces (GUI `facetConfigs.js`
`displayName`, OQL parse `oql_lang._FIELDS`, OQL render `COLUMN_DISPLAY_NAMES`,
docs) and the registry carried no human label at all. #381 makes the registry
the source of truth and projects it everywhere.

Two pieces of metadata per property:

  * ``display_name`` — the short canonical label/word (the chip word: "year",
    "full text"). NOT a sentence — that's ``Field.docstring`` (a separate, longer
    description already on the field).
  * ``aliases`` — alternate *input spellings of the column name itself* that a
    parser (OQL) should accept for this property, e.g. ``default`` ⇄ "anywhere",
    "any field". This is the OQL-parse alias list.

NOT the same as ``core.alternate_names.ALTERNATE_NAMES``. That table is a bag of
fuzzy *search tokens* for the filter-discovery search box (e.g. ``is_global_south``
→ ["asia", "africa", "india", …], with "full"/"text" as separate tokens). Those
are not parseable column-name spellings, so #381 keeps them as a distinct concept
— ``aliases`` here is the canonical column-spelling list, ``alternate_names`` stays
the search-token bag. (Verified 2026-06-06; the EXPLORE assumption that they were
one list was wrong.)

Resolution order for a (entity_type, param) pair:
  1. an explicit entry in ``DISPLAY_NAME_OVERRIDES[entity_type][param]``
     (the curated, intentional labels — Phase 2 seeds these by reconciling the
     existing GUI + OQL words), else
  2. ``(humanize(param), [])`` — a mechanical default so every one of the ~824
     properties has a sane label day one and the long tail needs no hand work.

This module is pure data + pure functions: no Flask, no ES, no DB imports, so it
stays unit-testable in a minimal venv and importable from the boot-time
properties builder without side effects.
"""

from typing import Dict, List, Tuple

# Suffixes on a search field's `param` that are mechanical, not part of the human
# label: `title_and_abstract.search` → label derived from `title_and_abstract`,
# and the `.exact` variant shares the base field's label. Stripped before
# humanizing so the default for a search field reads naturally.
_SEARCH_SUFFIXES = (".search.exact", ".search.no_stem", ".search")


def humanize(param: str) -> str:
    """Mechanical fallback label for a property `param`.

    Strips search-field suffixes, then turns dotted/underscored segments into a
    plain spaced phrase: ``publication_year`` → "publication year",
    ``title_and_abstract.search`` → "title and abstract". Intentional labels are
    set in ``DISPLAY_NAME_OVERRIDES`` instead; this only needs to be non-empty and
    not embarrassing for the long tail.
    """
    base = param
    for suffix in _SEARCH_SUFFIXES:
        if base.endswith(suffix):
            base = base[: -len(suffix)]
            break
    return base.replace(".", " ").replace("_", " ").strip()


# Curated overrides — Phase 2 reconciles the existing 261 GUI `displayName`s and
# ~35 OQL words into ONE canonical label + alias list per property. Keyed by
# entity_type (the OQO get_rows / ENTITY_FIELDS_MODULES key) → param. The same
# `param` legitimately differs per entity (e.g. works `display_name` → "title" vs
# authors `display_name` → "name"), so this MUST be entity-aware.
#
# Shape: DISPLAY_NAME_OVERRIDES[entity_type][param] = {
#     "display_name": "<short canonical label>",
#     "aliases": ["<alt column spelling>", ...],   # optional; OQL-parse aliases
# }
DISPLAY_NAME_OVERRIDES: Dict[str, Dict[str, dict]] = {
    # (Phase 2 populates this. Empty here so Phase 1 ships the mechanism with the
    # humanize() default for every property and no behavior change yet.)
}


def resolve_display_name(entity_type: str, param: str) -> Tuple[str, List[str]]:
    """Resolve ``(display_name, aliases)`` for one property.

    Curated override wins; otherwise ``(humanize(param), [])``. Always returns a
    non-empty ``display_name`` for any non-empty ``param``.
    """
    override = DISPLAY_NAME_OVERRIDES.get(entity_type, {}).get(param)
    if override:
        display_name = override.get("display_name") or humanize(param)
        aliases = list(override.get("aliases", []))
        return display_name, aliases
    return humanize(param), []
