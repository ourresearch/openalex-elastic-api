#!/usr/bin/env python3
"""Client ⊆ server invariant for the OQLO property catalog (#294, re-homed into
elastic-api by #331 Phase 3).

The openalex-gui client (`facetConfigs.js`) is a deliberately-curated SUBSET of
server query capability. The surviving, meaningful invariant from #294 is: every
client column that claims a SERVER-BACKED action (filter / group_by / sort) must
actually exist in the live server property catalog for its entity. This script
makes that invariant explicit and re-runnable in CI, closing #294's punted
"ongoing sync" item.

Server catalog = the live in-memory `ENTITY_PROPERTIES` built at boot from the
server's own `Field` objects (`core/properties.py`) — the same data `GET
/properties` serves. Client catalog = `scripts/client_registry.json`, a VENDORED
snapshot of `facetConfigs.js` (refresh it with `scripts/extract_client_registry.mjs`
run against a local openalex-gui checkout). It is vendored, not live-fetched, so
CI has no cross-repo dependency; a stale client snapshot can only MISS new drift,
never invent a false failure.

    PYTHONPATH=. python scripts/check_client_subset.py

Exit 0 = invariant holds. Exit 1 = a client column claims a server-backed action
on a column the server catalog doesn't have (drift).
"""
import json
import os
import sys

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

CLIENT_PATH = os.path.join(_REPO_ROOT, "scripts", "client_registry.json")
CLIENT = json.load(open(CLIENT_PATH))

from core.properties import build_properties  # noqa: E402

# {entity_type: {property_name: Property}} — membership is by key, so the Property
# value type is irrelevant here (we only ask "does this column exist?").
SERVER = build_properties()

# Actions that assert a server capability (vs display-only edit/column).
# `column` is DELIBERATELY not here (#450): the GUI's `column` action means "can
# be a SERP table column", rendered by CLIENT-SIDE extraction of nested paths
# (e.g. `open_access.is_oa`) from full result objects — NOT the server `column`
# capability (the top-level `?select=` vocabulary). Measured 2026-06-12: 36/125
# GUI column facets are not server-selectable, all legitimately. Reconciling the
# two `column` vocabularies belongs to the facetConfigs-generation endgame
# (OQLO charter decision 19), not this gate.
SERVER_BACKED_ACTIONS = {"filter", "group_by", "sort"}

# Client entity label -> server catalog entity key, where they differ.
ENTITY_MAP = {"types": "work-types"}

# Client entities that are NOT queryable server catalog entities (reference
# lookups with no fields_dict). Columns here can't be in the catalog; skipped
# with an explicit note rather than counted as drift.
NON_REGISTRY_ENTITIES = {"oa-statuses"}

# Documented not-drift exceptions: (entity, column) client affordances that are
# intentionally NOT catalog columns because they use a special transport.
# `apc_sum` / `cited_by_count_sum` are group-by SUMS sent as boolean params
# (`apc_sum=true`), not `group_by=apc_sum`; the server returns the totals in
# `meta`.
ALLOWLIST = {
    ("works", "apc_sum"),
    ("works", "cited_by_count_sum"),
}


def server_entity(client_ent):
    return ENTITY_MAP.get(client_ent, client_ent)


def main():
    misses = []
    skipped_entities = []
    checked = 0

    for client_ent, cols in CLIENT.items():
        if client_ent in NON_REGISTRY_ENTITIES:
            skipped_entities.append(client_ent)
            continue
        sent = server_entity(client_ent)
        server_cols = SERVER.get(sent)
        if server_cols is None:
            # An entity the client lists but the server catalog doesn't expose.
            actionable = [
                k for k, m in cols.items()
                if set(m.get("actions") or []) & SERVER_BACKED_ACTIONS
            ]
            if actionable:
                misses.append((client_ent, "<no server entity>", actionable[:5]))
            continue
        for col, meta in cols.items():
            acts = set(meta.get("actions") or []) & SERVER_BACKED_ACTIONS
            if not acts:
                continue
            checked += 1
            if col not in server_cols and (client_ent, col) not in ALLOWLIST:
                misses.append((client_ent, col, sorted(acts)))

    print(f"checked {checked} client columns with server-backed actions "
          f"across {len(CLIENT) - len(skipped_entities)} entities")
    if skipped_entities:
        print(f"skipped non-catalog reference entities: {skipped_entities}")
    if ALLOWLIST:
        print(f"allowlisted not-drift special-transport columns: "
              f"{sorted(ALLOWLIST)}")

    if misses:
        print(f"\nFAIL — {len(misses)} client column(s) claim a server-backed "
              f"action but are absent from the server property catalog:")
        for ent, col, acts in misses:
            print(f"  {ent}/{col}  (actions: {acts})")
        return 1

    print("\nPASS — client ⊆ server: every client filter/sort/group_by "
          "column exists in the live server property catalog.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
