#!/usr/bin/env python3
"""Audit: closed-vocab config yamls vs the live entity list endpoints (oxjob #616).

Tier-1 OQL value-domain validation rejects any enum value that isn't in the
hand-authored `values:` list of `config/<vocab>.yaml`, while the canonical
list is whatever the live endpoint (e.g. GET /work-types) serves — which is
also what the GUI builder's value picker fetches. The two drift silently:
work-types sat 5 types stale for months and broke `type is software`
(oxjob #603 round 25). This script diffs every closed vocab against its live
endpoint and reports three buckets per vocab:

  - MISSING from yaml (live-only): the picker offers it, the validator
    rejects it -> the #603 half-draft-chip bug. Fix by adding to the yaml.
  - STALE in yaml (yaml-only): validator accepts a value the canonical list
    no longer serves. Fix by removing (check live works-counts first).
  - NAME MISMATCH: same id, different display_name (cosmetic for Tier-1
    membership, but the yaml feeds autocomplete labels).

Intentional divergences go in ALLOWLIST below with a why-comment, so a run
is quiet unless something *new* drifts.

    PYTHONPATH=. python scripts/check_vocab_parity.py [--base URL] [--verbose]

Exit 0 = no unallowlisted drift. Exit 1 = drift (listed in output).
NOT wired into CI — manual runs only (Jason's call, 2026-07-15, oxjob #616).
"""
import argparse
import json
import os
import sys
import urllib.parse
import urllib.request

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

import yaml  # noqa: E402

# vocab -> live list endpoint path. The 9 wired Tier-1 vocabs plus the 3
# authored-but-unwired lists (licenses, source-types, institution-types)
# that #wire-unread-values-tier1 will wire.
VOCABS = {
    "countries": "/countries",
    "continents": "/continents",
    "languages": "/languages",
    "sdgs": "/sdgs",
    "work-types": "/work-types",
    "oa-statuses": "/oa-statuses",
    "domains": "/domains",
    "fields": "/fields",
    "subfields": "/subfields",
    "licenses": "/licenses",
    "source-types": "/source-types",
    "institution-types": "/institution-types",
}

# Intentional divergences: {vocab: {"live_only": {id, ...}, "yaml_only": {id, ...},
# "name_mismatch": {id, ...}}}. Ids are the yaml-style short form (e.g.
# "types/article"). EVERY entry needs a why-comment.
ALLOWLIST = {
    # (empty — the country display names went friendly AT THE SOURCE
    # (walden openalex.common.countries, 2026-07-15 #616), so the yaml and
    # the live endpoint agree again and the temporary countries allowlist is
    # gone. work-types was reconciled in #603 r25 / ddf57b4; non-canonical
    # works-data stragglers like types/grant are NOT served by /work-types so
    # they never appear in this diff. Add entries here only for divergences
    # Jason has signed off on keeping.)
}


def load_yaml_values(vocab):
    """-> {short_id: display_name} from config/<vocab>.yaml `values:`."""
    path = os.path.join(_REPO_ROOT, "config", f"{vocab}.yaml")
    with open(path) as f:
        doc = yaml.safe_load(f)
    values = doc.get("values") or []
    return {v["id"]: v.get("display_name") for v in values}


def fetch_live_values(vocab, base):
    """-> {short_id: display_name} from the live list endpoint, paged."""
    out = {}
    page, total = 1, None
    while total is None or len(out) < total:
        qs = urllib.parse.urlencode(
            {"per-page": 200, "page": page, "mailto": "team@ourresearch.org"})
        url = f"{base}{VOCABS[vocab]}?{qs}"
        with urllib.request.urlopen(url, timeout=60) as resp:
            doc = json.load(resp)
        total = doc["meta"]["count"]
        results = doc["results"]
        if not results:
            break  # defensive: don't loop forever if count > served rows
        for r in results:
            # live id is https://openalex.org/<ns>/<key>; yaml stores <ns>/<key>
            short = r["id"].replace("https://openalex.org/", "")
            out[short] = r.get("display_name")
        page += 1
    if len(out) != total:
        raise RuntimeError(
            f"{vocab}: fetched {len(out)} entities but meta.count={total} "
            "(transient ES state? rerun before trusting this diff)")
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--base", default="https://api.openalex.org")
    ap.add_argument("--verbose", action="store_true",
                    help="also print in-sync vocabs' counts")
    args = ap.parse_args()

    drift = 0
    for vocab in VOCABS:
        yaml_vals = load_yaml_values(vocab)
        live_vals = fetch_live_values(vocab, args.base)
        allow = ALLOWLIST.get(vocab, {})

        live_only = sorted(set(live_vals) - set(yaml_vals))
        yaml_only = sorted(set(yaml_vals) - set(live_vals))
        mismatched = sorted(i for i in set(yaml_vals) & set(live_vals)
                            if yaml_vals[i] != live_vals[i])

        buckets = [
            ("MISSING from yaml (live-only)", live_only,
             allow.get("live_only", set()), live_vals),
            ("STALE in yaml (yaml-only)", yaml_only,
             allow.get("yaml_only", set()), yaml_vals),
            ("NAME MISMATCH (yaml != live)", mismatched,
             allow.get("name_mismatch", set()), None),
        ]
        unallowed = [(label, [i for i in ids if i not in allowed], names)
                     for label, ids, allowed, names in buckets]
        n_drift = sum(len(ids) for _, ids, _ in unallowed)
        drift += n_drift

        status = "DRIFT" if n_drift else "ok"
        print(f"== {vocab}: {status}  (yaml {len(yaml_vals)}, live {len(live_vals)})")
        for label, ids, names in unallowed:
            if not ids:
                continue
            print(f"  {label}: {len(ids)}")
            for i in ids:
                if names is None:  # name mismatch: show both sides
                    print(f"    {i}: yaml={yaml_vals[i]!r} live={live_vals[i]!r}")
                else:
                    print(f"    {i}  ({names[i]})")
        allowed_n = sum(len(allow.get(k, ()))
                        for k in ("live_only", "yaml_only", "name_mismatch"))
        if allowed_n and args.verbose:
            print(f"  ({allowed_n} allowlisted divergences suppressed)")

    if drift:
        print(f"\nFAIL: {drift} unallowlisted drifted entries. Sync the yaml "
              "to the live list (the canonical-mirror rule, #603) or — for an "
              "intentional divergence — add an allowlist entry HERE with a "
              "why-comment.")
        return 1
    print("\nOK: all 12 closed vocabs match their live endpoints "
          "(modulo the documented allowlist).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
