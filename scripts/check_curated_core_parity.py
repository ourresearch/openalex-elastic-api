#!/usr/bin/env python3
"""CI gate: strict GUI==OQL parity for the CURATED core (oxjob #573).

#569/#572 made the per-entity FALLBACK vocabulary mechanically equal to the GUI
filter set. This closes the other half: every CURATED OQL word (an
`oql_lang._FIELDS` row) must be GUI-filter-faceted on every entity where it
parses — else OQL-only vocabulary re-emerges (the "three sets" confusion
Jason's 2026-07-06 parity decision forbids).

A curated word parses on entity E iff its entity-resolved column exists in E's
property catalog; the GUI side is the vendored scripts/client_registry.json.

Documented exclusion classes (not picker vocabulary):
  - date axes + bounds (kind "date"): the GUI filters dates via year-range
    facets; from_*/to_* columns are the OQL date-axis routing plumbing
  - self-ids (`ids.openalex` family): you navigate to an id, you don't facet it
  - search scopes (kind "search") + `collection` kind: separate UI surfaces
  - the `locations` entity: no GUI picker page

    PYTHONPATH=. python scripts/check_curated_core_parity.py

Exit 0 = parity holds. Exit 1 = a curated word parses somewhere the GUI has no
filter facet (message lists the pairs; fix by adding the GUI facet — or, if a
class is genuinely not picker material, add it to the documented exclusions
HERE, deliberately).
"""
import json
import os
import sys

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

ENTITY_ALIAS = {"work-types": "types"}   # server catalog name -> GUI name
EXCLUDED_ENTITIES = {"locations"}
SELF_ID_COLUMNS = {"ids.openalex", "id", "openalex", "openalex_id"}


def main():
    from core.properties import ENTITY_PROPERTIES
    from query_translation.oql_lang import _FIELDS, _entity_resolve_field

    reg = json.load(open(os.path.join(_REPO_ROOT, "scripts", "client_registry.json")))
    missing = []
    for ent, props in ENTITY_PROPERTIES.items():
        if ent in EXCLUDED_ENTITIES:
            continue
        gui_ent = ENTITY_ALIAS.get(ent, ent)
        if gui_ent not in reg:
            continue
        gui_filter = {k for k, v in dict(reg[gui_ent]).items()
                      if "filter" in (v.get("actions") or [])}
        seen = set()
        for _spellings, fld in _FIELDS:
            if fld.kind in ("search", "collection", "date"):
                continue
            col = _entity_resolve_field(fld, ent).column
            if col in SELF_ID_COLUMNS or col not in (props or {}) or col in seen:
                continue
            seen.add(col)
            if col not in gui_filter:
                missing.append((ent, col, fld.oql))

    if missing:
        print("FAIL — curated OQL words parse where the GUI has no filter facet "
              f"({len(missing)} pairs):")
        for ent, col, word in sorted(missing):
            print(f"  {ent}: {col}  (OQL word: {word!r})")
        print("Fix: add the GUI filter facet (openalex-gui facetConfigs.js), refresh "
              "scripts/client_registry.json (node scripts/extract_client_registry.mjs), "
              "and regen the allowlists — or add a documented exclusion class here, "
              "deliberately.")
        return 1
    print("OK: every curated OQL word is GUI-filter-faceted everywhere it parses "
          "(modulo the documented exclusion classes).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
