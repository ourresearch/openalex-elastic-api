#!/usr/bin/env python3
"""CI staleness gate for query_translation/input_alias_columns.py (oxjob #569).

Recomputes the two input-alias allowlists from the vendored GUI facet registry
(scripts/client_registry.json) + the curated extras, and fails when the
committed snapshot differs — so a GUI facet change (arriving via the routine
client_registry.json refresh) is LOUD here instead of silently not parsing in
OQL. Runs in the properties-gate workflow next to check_client_subset.py.

    PYTHONPATH=. python scripts/check_input_alias_columns.py

Exit 0 = snapshot matches. Exit 1 = drift (message says how to fix).
"""
import os
import sys

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)


def main():
    from scripts.regen_input_alias_columns import compute
    from query_translation.input_alias_columns import (
        INPUT_ALIAS_COLUMNS, GUI_FACETED_COLUMNS_BY_ENTITY)

    want_input, want_by_entity = compute()
    problems = []

    def diff(label, want, got):
        missing = sorted(want - got)
        extra = sorted(got - want)
        if missing:
            problems.append(f"{label}: snapshot MISSING {missing}")
        if extra:
            problems.append(f"{label}: snapshot has EXTRA {extra}")

    diff("INPUT_ALIAS_COLUMNS", want_input, set(INPUT_ALIAS_COLUMNS))
    for ent in sorted(set(want_by_entity) | set(GUI_FACETED_COLUMNS_BY_ENTITY)):
        diff(f"GUI_FACETED_COLUMNS_BY_ENTITY[{ent}]",
             set(want_by_entity.get(ent, ())),
             set(GUI_FACETED_COLUMNS_BY_ENTITY.get(ent, ())))

    if problems:
        print("STALE: query_translation/input_alias_columns.py has drifted from "
              "scripts/client_registry.json (+ curated extras).")
        for p in problems:
            print(f"  - {p}")
        print("Fix: PYTHONPATH=. python scripts/regen_input_alias_columns.py "
              "(and commit the result). If the GUI itself changed, refresh the "
              "vendored registry first: node scripts/extract_client_registry.mjs.")
        return 1
    print("OK: input_alias_columns.py matches the derived allowlists.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
