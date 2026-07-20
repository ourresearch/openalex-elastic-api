"""oxjob #331 Phase 3 — semantic diff classifier for the /properties contract.

Given two rendered `/properties` snapshots (the one committed at this push's git
BASE and the one committed at HEAD), classify the change as MAJOR / MINOR / none
per docs/PROPERTIES_VERSIONING.md, then assert that the `PROPERTIES_VERSION`
delta (read from each snapshot's `meta.version`) matches that class. This is the
mechanical "bump rule" half of the CI drift gate — the staleness half lives in
`scripts/render_properties.py --check`.

Everything here is pure stdlib (no app boot, no third-party deps) so it runs fast
in CI and is unit-testable in isolation: the classification operates only on the
two committed JSON snapshots, never on the live catalog.

The bump rule (docs/PROPERTIES_VERSIONING.md):
    MINOR  — purely additive: add an entity / property / operator / action /
             alias; add or tweak a display_name (#381 — labels are display
             metadata, not query semantics); ANY change to a property's `category`
             (#441 — a nullable, ungated organizational grouping; add / change /
             remove are all MINOR, none can break a query); ANY change to
             `supported_by` (#420 — descriptive metadata about OTHER surfaces:
             gui facet picker / documented REST; same weight as category).
    MAJOR  — anything that could invalidate a previously-valid query: remove an
             entity/property/operator/action/alias, rename a property (= remove + add,
             so the removal side already forces MAJOR), change a property's
             `type`, or change its cross-type `entity_type`, or drop a display_name.
    none   — the properties payload is byte-identical (meta is ignored here).

Exact-match policy (deliberately strict — the whole point of #331 is a mechanical
gate, not judgement): the version delta must equal the change class.
    change none  → version must be unchanged
    change minor → version must be exactly +1 minor (e.g. 1.0.0 → 1.1.0)
    change major → version must be exactly +1 major, minor reset (1.4.0 → 2.0.0)
Over-bumping (MAJOR for an additive change) and under-bumping both FAIL, so the
published version is an exact, trustworthy description of the change.

Usage:
    # Compare two snapshot files directly (what the unit tests + manual use call):
    python scripts/classify_properties_diff.py --base OLD.json --current NEW.json

    # CI convenience: pull the BASE snapshot out of git (the push's `before` SHA)
    # and compare against the working-tree HEAD snapshot. If the BASE ref has no
    # snapshot (first publication of the artifact), the bump check is skipped.
    python scripts/classify_properties_diff.py --base-ref "$BEFORE_SHA"

Exit 0 = bump is correct (or skipped — no base). Exit 1 = wrong/missing bump.
"""
import argparse
import json
import os
import subprocess
import sys

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_SNAPSHOT = os.path.join(_REPO_ROOT, "docs", "properties-snapshot.json")
SNAPSHOT_REL = "docs/properties-snapshot.json"
VERSIONING_DOC = "docs/PROPERTIES_VERSIONING.md"


# --------------------------------------------------------------------------- #
# Pure classification logic (unit-tested in tests/functional/test_properties_gate.py)
# --------------------------------------------------------------------------- #

def classify_change(old, new):
    """Classify the change between two rendered /properties payloads.

    `old`/`new` are the parsed `{meta, properties}` dicts. Returns
    `(change_class, reasons)` where change_class is "none" | "minor" | "major"
    and `reasons` is a sorted list of human-readable strings. A single MAJOR
    reason makes the whole change MAJOR (the strictest class wins); the returned
    `reasons` then lists the MAJOR causes first, followed by any MINOR ones for
    context.
    """
    old_props = old.get("properties", {})
    new_props = new.get("properties", {})
    major, minor = [], []

    old_entities, new_entities = set(old_props), set(new_props)
    for e in sorted(old_entities - new_entities):
        major.append(f"entity removed: {e}")
    for e in sorted(new_entities - old_entities):
        minor.append(f"entity added: {e}")

    for e in sorted(old_entities & new_entities):
        op, np_ = old_props[e], new_props[e]
        old_names, new_names = set(op), set(np_)
        for name in sorted(old_names - new_names):
            major.append(f"property removed: {e}.{name}")
        for name in sorted(new_names - old_names):
            minor.append(f"property added: {e}.{name}")
        for name in sorted(old_names & new_names):
            o, n = op[name], np_[name]
            if o.get("type") != n.get("type"):
                major.append(
                    f"type changed: {e}.{name}: {o.get('type')} -> {n.get('type')}"
                )
            if o.get("entity_type") != n.get("entity_type"):
                major.append(
                    f"entity_type changed: {e}.{name}: "
                    f"{o.get('entity_type')} -> {n.get('entity_type')}"
                )
            oo, no = set(o.get("operators") or []), set(n.get("operators") or [])
            for removed in sorted(oo - no):
                major.append(f"operator removed: {e}.{name}: {removed}")
            for added in sorted(no - oo):
                minor.append(f"operator added: {e}.{name}: {added}")
            oa, na = set(o.get("actions") or []), set(n.get("actions") or [])
            for removed in sorted(oa - na):
                major.append(f"action removed: {e}.{name}: {removed}")
            for added in sorted(na - oa):
                minor.append(f"action added: {e}.{name}: {added}")
            # display_name (#381) is display metadata, not query semantics: adding or
            # tweaking a label breaks no query (MINOR); dropping it back to null
            # removes a contract field consumers may read (MAJOR).
            od, nd = o.get("display_name"), n.get("display_name")
            if od is None and nd is not None:
                minor.append(f"display_name added: {e}.{name}: {nd!r}")
            elif od is not None and nd is None:
                major.append(f"display_name removed: {e}.{name}")
            elif od != nd:
                minor.append(f"display_name changed: {e}.{name}: {od!r} -> {nd!r}")
            # aliases (#381) are parseable query-input spellings (like operators):
            # adding one is additive (MINOR); removing one can invalidate a query a
            # client was sending (MAJOR).
            oal, nal = set(o.get("aliases") or []), set(n.get("aliases") or [])
            for added in sorted(nal - oal):
                minor.append(f"alias added: {e}.{name}: {added}")
            for removed in sorted(oal - nal):
                major.append(f"alias removed: {e}.{name}: {removed}")
            # alternate_keys (#446) are accepted machine-key spellings of an identity
            # (same contract weight as aliases): folding one in is additive (MINOR);
            # dropping one stops the API accepting a spelling a client may send (MAJOR).
            oak, nak = (
                set(o.get("alternate_keys") or []),
                set(n.get("alternate_keys") or []),
            )
            for added in sorted(nak - oak):
                minor.append(f"alternate_key added: {e}.{name}: {added}")
            for removed in sorted(oak - nak):
                major.append(f"alternate_key removed: {e}.{name}: {removed}")
            # category (#441) is a nullable, best-effort ORGANIZATIONAL grouping with
            # no query-behavior effect and NO enforcement gate (it may be null by
            # design, and consumers must already handle null). So every category
            # transition — add, change, or remove (value -> null) — is MINOR: none can
            # invalidate a previously-valid query. (Contrast display_name, whose
            # removal is MAJOR because it drops a contract field clients read.)
            oc, nc = o.get("category"), n.get("category")
            if oc != nc:
                minor.append(f"category changed: {e}.{name}: {oc!r} -> {nc!r}")
            # bool_true/bool_false (#428) are nullable, descriptive boolean sentence
            # phrasings ("it's open access") with no query-behavior effect — same
            # contract weight as category, so every transition (add / change /
            # remove) is MINOR; consumers must already handle null (they fall back
            # to a raw true/false rendering).
            for key in ("bool_true", "bool_false"):
                ob, nb = o.get(key), n.get(key)
                if ob != nb:
                    minor.append(f"{key} changed: {e}.{name}: {ob!r} -> {nb!r}")
            # supported_by (#420) — which OTHER user-facing surfaces expose the
            # property (gui facet picker / documented classic REST). Descriptive
            # metadata about surfaces beyond this API: no transition changes what
            # a /properties consumer may validly send HERE, so add / change /
            # remove are all MINOR, like category. (OQL's raw-column_id parse
            # acceptance derives from it, but the OQL contract is gated by its
            # own test corpus, not PROPERTIES_VERSION.)
            osb, nsb = set(o.get("supported_by") or []), set(n.get("supported_by") or [])
            if osb != nsb:
                minor.append(
                    f"supported_by changed: {e}.{name}: "
                    f"{sorted(osb)} -> {sorted(nsb)}"
                )

    if major:
        return "major", major + minor
    if minor:
        return "minor", minor
    return "none", []


def parse_version(v):
    """Parse 'MAJOR.MINOR' or 'MAJOR.MINOR.PATCH' into a (major, minor, patch)
    tuple (patch defaults to 0). Raises ValueError on a malformed string."""
    parts = str(v).split(".")
    if len(parts) not in (2, 3):
        raise ValueError(f"malformed version: {v!r}")
    nums = [int(p) for p in parts]
    while len(nums) < 3:
        nums.append(0)
    return tuple(nums)


def classify_version_delta(old_v, new_v):
    """Classify the version bump old->new as 'none' | 'minor' | 'major' |
    'invalid'. 'invalid' covers any non-canonical move: a decrease, a skipped
    number, a minor bump that didn't reset on a major, or ANY use of the patch
    lane (the /properties contract has no PATCH — see docs/PROPERTIES_VERSIONING.md)."""
    om, oi, op = parse_version(old_v)
    nm, ni, npatch = parse_version(new_v)
    if (nm, ni, npatch) == (om, oi, op):
        return "none"
    # Canonical bumps always land on patch 0 (no patch lane exists).
    if npatch == 0 and op == 0:
        if nm == om + 1 and ni == 0:
            return "major"
        if nm == om and ni == oi + 1:
            return "minor"
    return "invalid"


def check_bump(old, new):
    """Tie the content change class to the version delta. Returns `(ok, message)`.

    Policy: the version delta must EXACTLY equal the content change class.
    `old`/`new` are parsed snapshot payloads; versions are read from each one's
    `meta.version` (after the staleness check, HEAD's meta.version is guaranteed
    == the live PROPERTIES_VERSION constant).
    """
    change_class, reasons = classify_change(old, new)
    old_v = old.get("meta", {}).get("version")
    new_v = new.get("meta", {}).get("version")
    try:
        version_delta = classify_version_delta(old_v, new_v)
    except ValueError as exc:
        return False, f"FAIL — cannot parse PROPERTIES_VERSION: {exc}"

    detail = "\n".join(f"    - {r}" for r in reasons)

    if change_class == "none":
        if version_delta == "none":
            return True, "OK — /properties contract unchanged; version unchanged."
        return False, (
            f"FAIL — PROPERTIES_VERSION changed ({old_v} -> {new_v}) but the "
            f"/properties contract content is unchanged. Version moves iff the "
            f"contract moves; revert the spurious bump."
        )

    required = (
        "1.x.0 -> 2.0.0 (MAJOR)" if change_class == "major"
        else "1.x.0 -> 1.(x+1).0 (MINOR)"
    )
    if version_delta == change_class:
        return True, (
            f"OK — {change_class.upper()} change, PROPERTIES_VERSION correctly "
            f"bumped {old_v} -> {new_v}.\n{detail}"
        )
    return False, (
        f"FAIL — the /properties contract has a {change_class.upper()} change but "
        f"PROPERTIES_VERSION went {old_v} -> {new_v} "
        f"(classified: {version_delta}).\n"
        f"  Required bump: {required}.\n"
        f"  A HUMAN (Jason or Casey) must set PROPERTIES_VERSION in "
        f"core/properties.py — agents must NOT self-bump.\n"
        f"  See {VERSIONING_DOC}.\n"
        f"  Change details:\n{detail}"
    )


# --------------------------------------------------------------------------- #
# I/O + CLI
# --------------------------------------------------------------------------- #

def _load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _git_show(ref, rel_path):
    """Return the bytes of `rel_path` at git `ref`, or None if it doesn't exist
    there (e.g. the artifact didn't exist yet at the base commit)."""
    try:
        out = subprocess.run(
            ["git", "show", f"{ref}:{rel_path}"],
            cwd=_REPO_ROOT,
            capture_output=True,
            check=True,
        )
        return out.stdout
    except subprocess.CalledProcessError:
        return None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", help="Path to the BASE snapshot JSON file.")
    parser.add_argument(
        "--current",
        default=DEFAULT_SNAPSHOT,
        help="Path to the HEAD snapshot JSON file (default: committed snapshot).",
    )
    parser.add_argument(
        "--base-ref",
        help="Git ref to read the BASE snapshot from (e.g. the push 'before' SHA). "
        "Mutually exclusive with --base.",
    )
    args = parser.parse_args()

    new = _load(args.current)

    if args.base_ref:
        # All-zeros SHA = new branch / no prior commit. No base → skip.
        if set(args.base_ref) <= {"0"}:
            print("SKIP — no base ref (new branch); bump check not applicable.")
            return 0
        raw = _git_show(args.base_ref, SNAPSHOT_REL)
        if raw is None:
            print(
                f"SKIP — {SNAPSHOT_REL} does not exist at {args.base_ref[:12]} "
                f"(first publication of the artifact); bump check not applicable."
            )
            return 0
        old = json.loads(raw)
    elif args.base:
        old = _load(args.base)
    else:
        parser.error("provide --base or --base-ref")

    ok, message = check_bump(old, new)
    print(message)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
