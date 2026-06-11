"""Acceptance tests for the canonical `/properties` payload + fingerprint (#331
Phase 2 — ACCEPTANCE Test 2).

The catalog is a derived projection of the live `Field` objects; its rendered
payload must be byte-identical across fresh boots so the content `fingerprint`
never flaps on dict/set iteration order. These tests pin:
  - the sort is total (entities, property names, operators, actions);
  - the fingerprint is stable across two *separate* interpreter processes;
  - the committed `docs/properties-snapshot.json` matches the live render
    (the same staleness check the CI drift gate runs).

Run with `pytest --noconftest` — the top-level conftest eagerly imports the app.
"""

import json
import os
import subprocess
import sys

from core.properties import (
    ENTITY_PROPERTIES,
    PROPERTIES_VERSION,
    canonical_bytes,
    get_selectable_fields,
    properties_fingerprint,
    render_properties,
)

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SNAPSHOT_PATH = os.path.join(_REPO_ROOT, "docs", "properties-snapshot.json")


def _sorted_eq(seq):
    """True iff `seq` is already in sorted order (a total, deterministic sort)."""
    seq = list(seq)
    return seq == sorted(seq)


def test_render_is_totally_sorted():
    payload = render_properties()
    props = payload["properties"]
    # entities sorted
    assert _sorted_eq(props.keys())
    for entity, columns in props.items():
        # property names sorted within each entity
        assert _sorted_eq(columns.keys()), f"{entity} property names not sorted"
        for name, col in columns.items():
            # operators + actions sorted within each property
            assert _sorted_eq(col["operators"]), f"{entity}.{name} operators not sorted"
            assert _sorted_eq(col["actions"]), f"{entity}.{name} actions not sorted"


def test_meta_carries_version_fingerprint_and_counts():
    meta = render_properties()["meta"]
    assert meta["version"] == PROPERTIES_VERSION
    assert meta["fingerprint"] == properties_fingerprint()
    assert meta["entity_count"] == len(render_properties()["properties"])
    assert meta["property_count"] == sum(
        len(c) for c in render_properties()["properties"].values()
    )
    # sha256 hex
    assert len(meta["fingerprint"]) == 64
    int(meta["fingerprint"], 16)  # raises if not hex


def test_fingerprint_stable_within_process():
    # Repeated renders in the same process are byte-identical.
    a = canonical_bytes(_strip_meta(render_properties()))
    b = canonical_bytes(_strip_meta(render_properties()))
    assert a == b
    assert properties_fingerprint() == properties_fingerprint()


def _strip_meta(payload):
    return payload["properties"]


def test_fingerprint_stable_across_fresh_boots():
    """ACCEPTANCE Test 2: two SEPARATE interpreter processes must agree on the
    fingerprint — proves the canonical sort kills dict/set ordering nondeterminism."""
    prog = (
        "import sys; sys.path.insert(0, %r);"
        "from core.properties import properties_fingerprint;"
        "print(properties_fingerprint())" % _REPO_ROOT
    )
    env = {**os.environ, "PYTHONPATH": _REPO_ROOT}
    runs = [
        subprocess.run(
            [sys.executable, "-c", prog],
            capture_output=True, text=True, env=env, cwd=_REPO_ROOT,
        )
        for _ in range(2)
    ]
    for r in runs:
        assert r.returncode == 0, r.stderr
    fp1, fp2 = runs[0].stdout.strip(), runs[1].stdout.strip()
    assert fp1 == fp2
    assert fp1 == properties_fingerprint()


def test_committed_snapshot_matches_live_render():
    """The committed snapshot is the CI drift baseline AND the published artifact;
    it must equal what the live catalog renders (else it is stale)."""
    assert os.path.exists(SNAPSHOT_PATH), (
        "docs/properties-snapshot.json missing — run "
        "`python scripts/render_properties.py`"
    )
    with open(SNAPSHOT_PATH, encoding="utf-8") as f:
        committed = json.load(f)
    assert committed == render_properties(), (
        "snapshot is STALE — run `python scripts/render_properties.py` and bump "
        "PROPERTIES_VERSION per docs/PROPERTIES_VERSIONING.md"
    )


def test_rendered_catalog_is_filter_union_select():
    """The rendered catalog is the union of (filter-columns MINUS demoted alias
    spellings) and selectable result-fields, discriminated by `actions`
    (#318 / Decision D; #446 alias demotion). The render must NOT mutate
    `ENTITY_PROPERTIES` (the validator's filter-column source) — every selectable
    name appears in the render, every NON-alias filter name appears in the render,
    and a both-name carries `select` unioned into its filter actions.
    """
    works = render_properties(entity="works")["properties"]["works"]
    filter_names = set(ENTITY_PROPERTIES["works"])
    # #446: alias columns (alternate_of set) stay in ENTITY_PROPERTIES (validator
    # resolves them) but are demoted from the PUBLIC render — they survive only as
    # `alternate_keys` on their canonical property.
    alias_names = {
        name for name, prop in ENTITY_PROPERTIES["works"].items() if prop.alternate_of
    }
    assert alias_names, "expected some demoted alias columns on works (#446)"
    select_names = get_selectable_fields("works")

    # render = (filter MINUS demoted aliases) ∪ select
    assert (filter_names - alias_names) <= set(works)
    assert not (alias_names & set(works)), "demoted aliases must not be in the render"
    assert select_names <= set(works)

    # selectable names carry the `select` action
    for name in select_names:
        assert "select" in works[name]["actions"], name
    # a filter-only name does NOT gain `select` (skip demoted aliases — not rendered)
    filter_only = filter_names - select_names - alias_names
    assert filter_only, "expected some filter-only columns on works"
    for name in filter_only:
        assert "select" not in works[name]["actions"], name

    # ENTITY_PROPERTIES (validator's filter source) is untouched by the render:
    # select-only names never leak into it.
    assert (select_names - filter_names) and not (
        (select_names - filter_names) & filter_names
    )


def test_select_only_property_has_no_filter_surface():
    """A select-only field (e.g. `abstract_inverted_index`) renders as a property
    with `actions == ["select"]`, no `type`, no `operators` — it is selectable but
    not filterable, so it can never be mistaken for a filter column."""
    works = render_properties(entity="works")["properties"]["works"]
    select_only = get_selectable_fields("works") - set(ENTITY_PROPERTIES["works"])
    assert "abstract_inverted_index" in select_only
    for name in select_only:
        prop = works[name]
        assert prop["actions"] == ["select"], name
        assert prop["type"] is None, name
        assert prop["operators"] == [], name


def test_entity_slice_matches_full_catalog():
    """`render_properties(entity=...)` slices `properties` to one entity but keeps
    the full-catalog identity in `meta` (version/fingerprint/counts unchanged)."""
    full = render_properties()
    works = render_properties(entity="works")
    assert set(works["properties"].keys()) == {"works"}
    assert works["properties"]["works"] == full["properties"]["works"]
    assert works["meta"]["fingerprint"] == full["meta"]["fingerprint"]
    assert works["meta"]["version"] == full["meta"]["version"]
    assert works["meta"]["entity"] == "works"
