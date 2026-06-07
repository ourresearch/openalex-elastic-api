"""#381 label-consistency gate — unit tests for the pure comparator.

`check_label_consistency.compare()` takes the vendored client snapshot shape and a
plain {entity: {param: display_name}} projection of the registry, so it needs no app
boot / ES / DB. We drive it with small synthetic fixtures.
"""
import importlib

clc = importlib.import_module("scripts.check_label_consistency")


def test_matching_labels_pass():
    client = {"works": {"cited_by_count": {"displayName": "citation count"}}}
    server = {"works": {"cited_by_count": "citation count"}}
    misses, stats = clc.compare(client, server)
    assert misses == []
    assert stats["checked"] == 1


def test_case_insensitive_match():
    # the registry owns the word, the GUI owns casing (ACCEPTANCE out-of-scope).
    client = {"works": {"orcid": {"displayName": "ORCID"}}}
    server = {"works": {"orcid": "orcid"}}
    misses, _ = clc.compare(client, server)
    assert misses == []


def test_divergence_is_caught():
    client = {"authors": {"cited_by_count": {"displayName": "citations count"}}}
    server = {"authors": {"cited_by_count": "citation count"}}
    misses, stats = clc.compare(client, server)
    assert misses == [("authors", "cited_by_count", "citations count", "citation count")]
    assert stats["checked"] == 1


def test_displaynameverbatim_skipped():
    client = {"works": {"collection": {
        "displayName": "Work is in collection", "displayNameVerbatim": True}}}
    server = {"works": {"collection": "collection"}}
    misses, stats = clc.compare(client, server)
    assert misses == []
    assert stats["skipped_verbatim"] == 1
    assert stats["checked"] == 0


def test_gui_only_facet_skipped():
    # facet whose param has no registry property → can't reconcile, skip not fail.
    client = {"works": {"apc_sum": {"displayName": "APC sum"}}}
    server = {"works": {}}
    misses, stats = clc.compare(client, server)
    assert misses == []
    assert stats["skipped_no_param"] == 1


def test_no_displayname_skipped():
    client = {"works": {"x": {"displayName": None}}}
    server = {"works": {"x": "whatever"}}
    misses, stats = clc.compare(client, server)
    assert misses == []
    assert stats["skipped_no_displayname"] == 1


def test_param_alias_resolved():
    # GUI facet key `ids.orcid` maps to registry param `orcid`.
    client = {"authors": {"ids.orcid": {"displayName": "ORCID"}}}
    server = {"authors": {"orcid": "ORCID"}}
    misses, stats = clc.compare(client, server)
    assert misses == []
    assert stats["checked"] == 1
    assert clc.CLIENT_PARAM_ALIASES["ids.orcid"] == "orcid"


def test_entity_map_resolved():
    # client entity `types` -> server catalog entity `work-types`.
    client = {"types": {"cited_by_count": {"displayName": "wrong"}}}
    server = {"work-types": {"cited_by_count": "citation count"}}
    misses, _ = clc.compare(client, server)
    assert misses == [("types", "cited_by_count", "wrong", "citation count")]


def test_non_registry_entity_skipped():
    client = {"oa-statuses": {"is_oa": {"displayName": "anything"}}}
    server = {"oa-statuses": {"is_oa": "registry word"}}
    misses, stats = clc.compare(client, server)
    assert misses == []
    assert stats["checked"] == 0


def test_allowlist_suppresses_divergence(monkeypatch):
    monkeypatch.setattr(clc, "ALLOWLIST", {("authors", "cited_by_count"): "test"})
    client = {"authors": {"cited_by_count": {"displayName": "off"}}}
    server = {"authors": {"cited_by_count": "citation count"}}
    misses, _ = clc.compare(client, server)
    assert misses == []
