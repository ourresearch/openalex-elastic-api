#!/usr/bin/env python3
"""Label-consistency invariant: GUI displayName == registry display_name (#381).

The registry (`Field`/`Property` in `core/`) is the single source of truth for
each property's canonical human label. #381 reconciled the GUI's `facetConfigs.js`
`displayName`s to the registry; this gate keeps them from re-drifting.

For every client facet whose mapped param exists in the server property catalog,
assert `displayName` matches the registry `display_name` (case-insensitively — the
registry owns the *word*, the GUI owns casing/titleCase per ACCEPTANCE out-of-scope).

We deliberately SKIP, not fail:
  - GUI-only synthetic facets whose key has no registry param (e.g. composite or
    presentation-only chips). Same posture as check_client_subset.py: a client
    snapshot can only MISS drift, never invent it.
  - `displayNameVerbatim` facets — the GUI intentionally owns a verbatim sentence
    label there (the per-entity "<Entity> is in collection" chips, #367). ACCEPTANCE
    lists `displayNameVerbatim` as a GUI-only presentation concern, out of scope.
  - facets carrying no `displayName` at all (nothing to compare).

Server catalog = the live in-memory catalog built at boot from `Field` objects
(`core/properties.py`), same data `GET /properties` serves. Client catalog =
`scripts/client_registry.json`, a VENDORED snapshot of `facetConfigs.js` (refresh
with `scripts/extract_client_registry.mjs` against a local openalex-gui checkout).

    PYTHONPATH=. python scripts/check_label_consistency.py

Exit 0 = labels agree. Exit 1 = a client facet's displayName diverges from the
registry display_name for the same property (drift).
"""
import json
import os
import sys

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

CLIENT_PATH = os.path.join(_REPO_ROOT, "scripts", "client_registry.json")

# Client entity label -> server catalog entity key, where they differ.
ENTITY_MAP = {"types": "work-types"}

# Client entities that are NOT queryable server catalog entities (no fields_dict).
NON_REGISTRY_ENTITIES = {"oa-statuses"}

# GUI facet key -> server catalog param name, for the few facets whose key differs
# from the registry property name (the #381 Phase-4 alias-param fold-in).
CLIENT_PARAM_ALIASES = {
    "ids.orcid": "orcid",
    "ids.ror": "ror",
    "publisher": "host_organization",
}

# Documented label divergences we accept as not-drift. Keep empty unless there's a
# real, recorded reason — the whole point of #381 is that this stays empty.
# Shape: {(entity, facet_key): "why"}.
ALLOWLIST = {}


def server_entity(client_ent):
    return ENTITY_MAP.get(client_ent, client_ent)


def compare(client, server_labels):
    """Pure comparison core (no app boot, no I/O) so it's unit-testable.

    client        — {entity: {facet_key: {displayName, displayNameVerbatim, ...}}}
                    (the shape of scripts/client_registry.json).
    server_labels — {server_entity: {param: display_name_str}} — the registry's
                    canonical labels (main() projects build_properties() into this).

    Returns (misses, stats) where misses is a list of
    (entity, facet_key, client_label, server_label) tuples and stats is a dict
    of the skip/checked counters.
    """
    misses = []
    stats = {
        "checked": 0,
        "skipped_verbatim": 0,
        "skipped_no_param": 0,
        "skipped_no_displayname": 0,
    }

    for client_ent, cols in client.items():
        if client_ent in NON_REGISTRY_ENTITIES:
            continue
        sent = server_entity(client_ent)
        server_cols = server_labels.get(sent) or {}
        for col, meta in cols.items():
            if meta.get("displayNameVerbatim"):
                stats["skipped_verbatim"] += 1
                continue
            client_label = meta.get("displayName")
            if not client_label:
                stats["skipped_no_displayname"] += 1
                continue
            param = CLIENT_PARAM_ALIASES.get(col, col)
            if param not in server_cols:
                # GUI-only synthetic facet — no registry property to reconcile to.
                stats["skipped_no_param"] += 1
                continue
            stats["checked"] += 1
            server_label = server_cols.get(param) or ""
            if client_label.lower() != server_label.lower():
                if (client_ent, col) in ALLOWLIST:
                    continue
                misses.append((client_ent, col, client_label, server_label))

    return misses, stats


def main():
    client = json.load(open(CLIENT_PATH))

    from core.properties import build_properties  # noqa: E402

    # Project the live catalog {entity: {param: Property}} into the plain
    # {entity: {param: display_name_str}} the pure comparator expects.
    server_labels = {
        ent: {param: (prop.display_name or "") for param, prop in cols.items()}
        for ent, cols in build_properties().items()
    }

    misses, stats = compare(client, server_labels)

    print(f"checked {stats['checked']} client facet labels against the server catalog")
    print(f"skipped: {stats['skipped_verbatim']} displayNameVerbatim, "
          f"{stats['skipped_no_param']} GUI-only (no registry param), "
          f"{stats['skipped_no_displayname']} without a displayName")
    if ALLOWLIST:
        print(f"allowlisted divergences: {sorted(ALLOWLIST)}")

    if misses:
        print(f"\nFAIL — {len(misses)} client facet label(s) diverge from the "
              f"registry display_name:")
        for ent, col, client_label, server_label in misses:
            print(f"  {ent}/{col}: gui={client_label!r} != registry={server_label!r}")
        return 1

    print("\nPASS — every reconciled client facet label matches the registry "
          "display_name.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
