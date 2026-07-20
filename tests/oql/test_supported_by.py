"""#420 — `Property.supported_by` behavioral pins.

The registry-native successor of the retired generated allowlists
(`query_translation/input_alias_columns.py`): each property carries the set of
user-facing surfaces that expose it ("gui" = openalex-gui filter facet, computed
from the vendored scripts/client_registry.json; "oxurl" = documented classic
REST, the curated works list in core/oxurl_documented.py). OQL's raw-column_id
fallback doors gate on it: works accepts `supported_by` non-empty (GUI∪docs),
non-works accepts `'gui' in supported_by` (#572 strict GUI==OQL parity).
"""
from core.oxurl_documented import OXURL_DOCUMENTED_WORKS_COLUMNS
from core.properties import ENTITY_PROPERTIES
from query_translation import oql_lang


WORKS = ENTITY_PROPERTIES["works"]


def test_percentile_trio_is_supported_and_raw_id_parses():
    # The #406 casualties this job's README exists to re-cover: GUI-faceted,
    # so `supported_by` carries "gui" and the raw column_id parses via the
    # works fallback door with NO curated `_FIELDS` raw-id alias.
    for cid in (
        "citation_normalized_percentile.value",
        "citation_normalized_percentile.is_in_top_1_percent",
        "citation_normalized_percentile.is_in_top_10_percent",
    ):
        assert "gui" in WORKS[cid].supported_by, cid
        assert oql_lang._registry_fallback_field(cid) is not None, cid


def test_oxurl_documented_column_is_supported():
    # Documented-API-only columns (curated oxurl list, not GUI-faceted) must
    # exist and their raw ids parse via the works door — the docs half of the
    # GUI∪docs parity rule. (Membership computed, not hard-coded: the curated
    # list and the GUI facets both drift by design.)
    oxurl_only = [
        cid for cid, prop in WORKS.items()
        if prop.supported_by == frozenset({"oxurl"})
    ]
    assert oxurl_only, "expected at least one docs-only works column"
    checked = 0
    for cid in oxurl_only:
        # curated spellings + search/collection columns route via their own
        # paths; every other docs-only column must hit the fallback door.
        ops = set(WORKS[cid].operators or [])
        if cid.lower() in oql_lang._ALIAS or ops & {"search", "collection"}:
            continue
        assert oql_lang._registry_fallback_field(cid) is not None, cid
        checked += 1
    assert checked, "expected at least one docs-only column on the fallback door"


def test_unsupported_internal_column_does_not_parse():
    # Columns surfaced NOWHERE (empty supported_by) must not get a raw-id
    # fallback Field — the Jason 2026-06-08 GUI+docs-parity rule. Skip curated
    # spellings (`_ALIAS`): those parse via their own curated path by design.
    internal = [
        cid for cid, prop in WORKS.items()
        if not prop.supported_by and cid.lower() not in oql_lang._ALIAS
    ]
    assert internal, "expected at least one internal-only works column"
    for cid in internal:
        assert oql_lang._registry_fallback_field(cid) is None, cid


def test_non_works_gates_on_gui_membership():
    # authors: `orcid` is GUI-faceted -> in the entity fallback index;
    # oxurl never applies off works (the curated list is works-only).
    authors = ENTITY_PROPERTIES["authors"]
    assert "gui" in authors["orcid"].supported_by
    assert "orcid" in oql_lang._entity_fallback("authors")
    for prop in authors.values():
        assert "oxurl" not in prop.supported_by


def test_supported_by_serializes_sorted():
    prop = WORKS["topics.id"]  # GUI-faceted AND documented
    assert prop.supported_by == frozenset({"gui", "oxurl"})
    assert prop.serialize()["supported_by"] == ["gui", "oxurl"]


def test_oxurl_curated_list_stays_within_the_registry():
    # Every curated oxurl column must exist in the live works catalog — a
    # renamed/removed Field must prune its curated entry (the old regen script
    # silently intersected; now we fail loud here instead).
    missing = sorted(OXURL_DOCUMENTED_WORKS_COLUMNS - set(WORKS))
    assert not missing, f"curated oxurl columns absent from works catalog: {missing}"
