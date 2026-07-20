"""Scoped-search params: `search.<field>[.exact]=` → filter-column twin (oxjob #422, #633).

Top-level scoped-search params thread into `parse_url_to_oqo` via the
`scoped_searches` dict (oxjob #633; this replaced the #422 fold-into-filter-string
shim, which corrupted comma-containing values at the clause splitter).
`scoped_search_column` maps each param to the column the ENGINE executes it as
(`core/params.py` scope map ≡ `core/fields.py SearchField`, count-identical).
`search.<field>.exact=<v>` must emit the CANONICAL column order
`<field>.search.exact` — NOT the malformed `<field>.exact.search` that the
registry rejects as `invalid_column`.

Pure: no app boot (url_parser + validator import without Flask). Run with
    PYTHONPATH=. pytest tests/oql/test_scoped_search_fold.py -q --noconftest
"""
import pytest

import tests.oql._qt_loader  # noqa: F401  (installs the pure query_translation stub)

from query_translation.url_parser import (  # noqa: E402
    parse_url_to_oqo,
    scoped_search_column,
)
from query_translation.validator import validate_oqo  # noqa: E402
from query_translation.oql_lang import render  # noqa: E402


def _parse_and_validate(params, entity_type="works", **kw):
    oqo = parse_url_to_oqo(entity_type, scoped_searches=dict(params), **kw)
    return oqo, validate_oqo(oqo)


# --- the column map is the engine's own scope map -----------------------------

def test_exact_maps_to_canonical_search_exact_order():
    # `.exact` is pulled off, re-attached AFTER `.search` (canonical order).
    assert (
        scoped_search_column("search.title_and_abstract.exact", "works")
        == "title_and_abstract.search.exact"
    )


def test_exact_never_emits_malformed_exact_search_order():
    out = scoped_search_column("search.title_and_abstract.exact", "works")
    assert ".exact.search" not in out  # the #422 bug: order must not regress


def test_plain_scoped_search_maps_to_search_column():
    assert (
        scoped_search_column("search.title_and_abstract", "works")
        == "title_and_abstract.search"
    )


def test_unscoped_exact_is_fulltext_exact_on_works_only():
    # works: `search.exact=` ≡ filter=fulltext.search.exact (full_search_query_exact
    # both doors). Off-works the engine silently degrades exact to the plain
    # stemmed broad search, so the honest column there is text.search.
    assert scoped_search_column("search.exact", "works") == "fulltext.search.exact"
    assert scoped_search_column("search.exact", "authors") == "text.search"


def test_semantic_maps_to_canonical_semantic_column():
    # Same leaf parse_url_to_oqo's own semantic_search_string path builds.
    assert scoped_search_column("search.semantic", "works") == "abstract.search.semantic"


# --- scoped params thread into the OQO and validate ---------------------------

def test_exact_scoped_search_validates_and_keeps_value_verbatim():
    oqo, vr = _parse_and_validate(
        {"search.title_and_abstract.exact": "Windows AND (DLL OR DLLs)"})
    assert vr.valid, [getattr(e, "message", e) for e in vr.errors]
    leaf = oqo.to_dict()["filter_rows"][0]
    # Canonical column (NOT title_and_abstract.exact.search); the BARE value
    # stays bare (#633 — bare = no-stem AND/boolean semantics on the engine,
    # count-distinct from the quoted phrase, so quoting it would silently
    # rewrite the query; the old #568 auto-quote is reversed).
    assert leaf["column_id"] == "title_and_abstract.search.exact"
    assert leaf["value"] == "Windows AND (DLL OR DLLs)"


@pytest.mark.parametrize("field", ["title", "abstract", "title_and_abstract"])
def test_exact_scoped_search_generalizes_across_scoped_fields(field):
    _, vr = _parse_and_validate({f"search.{field}.exact": "foo"})
    assert vr.valid, [getattr(e, "message", e) for e in vr.errors]


def test_plain_scoped_search_still_validates():
    _, vr = _parse_and_validate({"search.title_and_abstract": "cancer"})
    assert vr.valid, [getattr(e, "message", e) for e in vr.errors]


def test_comma_in_value_stays_one_clause():
    # The reason scoped params must NOT ride the comma-joined filter string:
    # a free-text value containing a comma is still ONE search clause.
    oqo, vr = _parse_and_validate({"search.title": "cancer, treatment"})
    assert vr.valid, [getattr(e, "message", e) for e in vr.errors]
    rows = oqo.to_dict()["filter_rows"]
    assert len(rows) == 1
    assert rows[0]["value"] == "cancer, treatment"


def test_multiple_scoped_params_all_thread_and_join_as_and():
    # The engine ANDs simultaneous search.* params (_extract_all_search_params);
    # each becomes its own filter row.
    oqo, vr = _parse_and_validate({
        "search.title": "dark matter",
        "search.title_and_abstract.exact": "spin",
    })
    assert vr.valid, [getattr(e, "message", e) for e in vr.errors]
    cols = {r["column_id"] for r in oqo.to_dict()["filter_rows"]}
    assert cols == {"display_name.search", "title_and_abstract.search.exact"}


def test_scoped_search_coexists_with_filter_string():
    oqo, vr = _parse_and_validate(
        {"search.title": "dark matter"}, filter_string="type:article")
    assert vr.valid, [getattr(e, "message", e) for e in vr.errors]
    cols = [r.get("column_id") for r in oqo.to_dict()["filter_rows"]]
    assert "type" in cols and "display_name.search" in cols


# --- the exact AND-of-words OQL surface (#633) --------------------------------

def test_bare_multiword_exact_renders_exact_marker_and_roundtrips():
    # Bare multi-word on .exact = no-stem AND-of-words — a different query from
    # the quoted phrase (live: title.search.exact:cancer treatment = 224,070
    # vs :"cancer treatment" = 36,755). OQL surface: `exact <words>`, the
    # inverse of `stemmed "…"`.
    oqo, vr = _parse_and_validate({"search.title.exact": "cancer treatment"})
    assert vr.valid, [getattr(e, "message", e) for e in vr.errors]
    leaf = oqo.to_dict()["filter_rows"][0]
    assert leaf["column_id"] == "display_name.search.exact"
    assert leaf["value"] == "cancer treatment"
    oql = render(oqo)
    assert "has (exact cancer treatment)" in oql


def test_quoted_phrase_exact_still_renders_plain_quotes():
    oqo, _ = _parse_and_validate({"search.title.exact": '"cancer treatment"'})
    leaf = oqo.to_dict()["filter_rows"][0]
    assert leaf["value"] == '"cancer treatment"'
    assert 'has ("cancer treatment")' in render(oqo)
