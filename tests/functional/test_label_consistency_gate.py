"""oxjob #381 — unit tests for the label-consistency drift gate.

These exercise the PURE comparator in `scripts/check_label_consistency.py`
(`compare(client, server_labels)`) against hand-built catalogs — no app boot, no
ES, no GUI checkout. They pin the anti-re-drift rule: every reconciled client
facet `displayName` must equal the registry `display_name` (case-insensitively),
with documented skips (verbatim labels, GUI-only synthetic facets, missing labels)
and the Phase-4 alias-param fold-in.

Run with `pytest --noconftest` — the top-level conftest eagerly imports the app;
this test only needs the stdlib-only comparator on sys.path.
"""
import importlib.util
import os

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_MOD_PATH = os.path.join(_REPO_ROOT, "scripts", "check_label_consistency.py")
_spec = importlib.util.spec_from_file_location("check_label_consistency", _MOD_PATH)
chk = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(chk)


def _facet(display_name, verbatim=False):
    return {"displayName": display_name, "displayNameVerbatim": verbatim}


# --------------------------------------------------------------------------- #
# matches → no misses
# --------------------------------------------------------------------------- #

def test_matching_label_is_not_a_miss():
    client = {"authors": {"cited_by_count": _facet("cited by count")}}
    server = {"authors": {"cited_by_count": "cited by count"}}
    misses, stats = chk.compare(client, server)
    assert misses == []
    assert stats["checked"] == 1


def test_case_insensitive_match():
    client = {"works": {"doi": _facet("DOI")}}
    server = {"works": {"doi": "doi"}}
    misses, stats = chk.compare(client, server)
    assert misses == []
    assert stats["checked"] == 1


# --------------------------------------------------------------------------- #
# divergence → miss
# --------------------------------------------------------------------------- #

def test_divergent_label_is_a_miss():
    client = {"authors": {"cited_by_count": _facet("citations count")}}
    server = {"authors": {"cited_by_count": "cited by count"}}
    misses, stats = chk.compare(client, server)
    assert misses == [("authors", "cited_by_count", "citations count", "cited by count")]
    assert stats["checked"] == 1


# --------------------------------------------------------------------------- #
# skips
# --------------------------------------------------------------------------- #

def test_verbatim_facets_are_skipped():
    client = {"works": {"collection": _facet("Work is in collection", verbatim=True)}}
    server = {"works": {"collection": "collection"}}
    misses, stats = chk.compare(client, server)
    assert misses == []
    assert stats["skipped_verbatim"] == 1
    assert stats["checked"] == 0


def test_gui_only_facet_without_registry_param_is_skipped():
    client = {"works": {"some_composite_chip": _facet("My Chip")}}
    server = {"works": {"doi": "doi"}}
    misses, stats = chk.compare(client, server)
    assert misses == []
    assert stats["skipped_no_param"] == 1
    assert stats["checked"] == 0


def test_facet_without_displayname_is_skipped():
    client = {"works": {"doi": {"displayName": None}}}
    server = {"works": {"doi": "doi"}}
    misses, stats = chk.compare(client, server)
    assert misses == []
    assert stats["skipped_no_displayname"] == 1


def test_non_registry_entity_is_skipped_entirely():
    # oa-statuses is a static GUI list, not a queryable server catalog entity.
    client = {"oa-statuses": {"anything": _facet("whatever it wants")}}
    server = {}
    misses, stats = chk.compare(client, server)
    assert misses == []
    assert stats["checked"] == 0


# --------------------------------------------------------------------------- #
# alias-param fold-in (Phase 4) + entity remap
# --------------------------------------------------------------------------- #

def test_client_param_alias_resolves_to_registry_param():
    # GUI facet key 'publisher' maps to registry param 'host_organization'.
    client = {"sources": {"publisher": _facet("publisher")}}
    server = {"sources": {"host_organization": "publisher"}}
    misses, stats = chk.compare(client, server)
    assert misses == []
    assert stats["checked"] == 1


def test_client_param_alias_still_detects_drift():
    client = {"works": {"ids.orcid": _facet("orcid id")}}
    server = {"works": {"orcid": "orcid"}}
    misses, stats = chk.compare(client, server)
    assert misses == [("works", "ids.orcid", "orcid id", "orcid")]


def test_entity_remap_types_to_work_types():
    # Client entity 'types' is the server catalog's 'work-types'.
    client = {"types": {"cited_by_count": _facet("cited by count")}}
    server = {"work-types": {"cited_by_count": "cited by count"}}
    misses, stats = chk.compare(client, server)
    assert misses == []
    assert stats["checked"] == 1


# --------------------------------------------------------------------------- #
# allowlist
# --------------------------------------------------------------------------- #

def test_allowlist_suppresses_a_known_divergence(monkeypatch):
    monkeypatch.setitem(chk.ALLOWLIST, ("authors", "cited_by_count"), "test reason")
    client = {"authors": {"cited_by_count": _facet("citations count")}}
    server = {"authors": {"cited_by_count": "cited by count"}}
    misses, _ = chk.compare(client, server)
    assert misses == []
