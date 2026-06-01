"""oxjob #334 — OQO list-entity coverage audit.

For every legacy list entity, answer:
  (1) Does core.registry.REGISTRY contain it?  (validator accepts the entity)
  (2) How many columns does it register?
  (3) Does query_translation.views._resolve_entity handle it?  (/query can execute)

No app boot / no ES needed — registry builds at import, and _resolve_entity only
imports per-entity fields modules. Run from repo root with PYTHONPATH=. .
"""
import importlib

from core.registry import REGISTRY
from query_translation.views import _resolve_entity, NATIVE_ENTITY_TYPES
from core.exceptions import APIQueryParamsError

# Legacy list entities, by their canonical /<entity> route name (OQO get_rows form).
LEGACY_LIST_ENTITIES = [
    "works", "authors", "institutions", "sources", "publishers", "funders",
    "topics", "keywords", "concepts", "domains", "fields", "subfields",
    "countries", "continents", "languages", "licenses", "sdgs",
    "source-types", "institution-types", "work-types", "awards", "locations",
    "oa-statuses", "raw-affiliation-strings",
]

print(f"{'entity':<24} {'in_registry':<12} {'#cols':<6} {'_resolve_entity':<16}")
print("-" * 64)
for ent in LEGACY_LIST_ENTITIES:
    in_reg = ent in REGISTRY
    ncols = len(REGISTRY.get(ent, {})) if in_reg else 0
    try:
        _resolve_entity(ent, connection="walden")
        resolves = "ok"
    except APIQueryParamsError:
        resolves = "RAISES 400"
    except Exception as e:
        resolves = f"ERR:{type(e).__name__}"
    flag = "" if (in_reg and resolves == "ok") or (not in_reg and resolves != "ok") else "  <-- MISMATCH"
    print(f"{ent:<24} {str(in_reg):<12} {ncols:<6} {resolves:<16}{flag}")

print()
print("Registry keys not in legacy list set:",
      sorted(set(REGISTRY) - set(LEGACY_LIST_ENTITIES)))
