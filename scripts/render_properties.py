"""oxjob #331 Phase 2 — render the canonical properties snapshot.

Boots the in-memory property catalog (importing `core.properties` is enough; no
ES, no `create_app()`), renders the canonical `/properties` payload, and writes
it pretty-printed (sorted keys) to `docs/properties-snapshot.json`. That file is
BOTH the CI drift baseline AND the published artifact offline consumers bundle —
the git diff of the snapshot is, by construction, the semantic diff of the
contract.

Usage (from repo root, `PYTHONPATH=.`):
    python scripts/render_properties.py            # regenerate the snapshot
    python scripts/render_properties.py --check     # exit 1 if snapshot is stale

The `--check` mode is what the Phase 3 CI drift gate calls to assert the
committed snapshot still matches the live catalog (staleness check). It does NOT
classify the semver bump — that's the gate's separate git-diff step.
"""
import argparse
import json
import os
import sys

# Repo root on sys.path so `core.*` imports work regardless of CWD.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from core.properties import render_properties  # noqa: E402

SNAPSHOT_PATH = os.path.join(_REPO_ROOT, "docs", "properties-snapshot.json")


def render_snapshot_text():
    """The canonical snapshot file contents: pretty-printed, sorted keys, one
    trailing newline. Matches what `--check` compares and the file we commit."""
    payload = render_properties()
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Exit 1 if docs/properties-snapshot.json differs from the live catalog.",
    )
    args = parser.parse_args()

    text = render_snapshot_text()

    if args.check:
        if not os.path.exists(SNAPSHOT_PATH):
            print(f"ERROR: snapshot missing at {SNAPSHOT_PATH}", file=sys.stderr)
            print("Run: python scripts/render_properties.py", file=sys.stderr)
            return 1
        with open(SNAPSHOT_PATH, encoding="utf-8") as f:
            committed = f.read()
        if committed != text:
            print(
                "ERROR: docs/properties-snapshot.json is STALE — it does not match "
                "the live property catalog.\n"
                "Regenerate it: python scripts/render_properties.py\n"
                "Then classify the diff and bump PROPERTIES_VERSION per "
                "docs/PROPERTIES_VERSIONING.md (human approval required).",
                file=sys.stderr,
            )
            return 1
        print("OK: snapshot matches the live property catalog.")
        return 0

    with open(SNAPSHOT_PATH, "w", encoding="utf-8") as f:
        f.write(text)
    payload = render_properties()
    print(
        f"Wrote {SNAPSHOT_PATH}\n"
        f"  version:     {payload['meta']['version']}\n"
        f"  fingerprint: {payload['meta']['fingerprint']}\n"
        f"  entities:    {payload['meta']['entity_count']}\n"
        f"  properties:  {payload['meta']['property_count']}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
