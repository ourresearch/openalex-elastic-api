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

def test_exact_boolean_value_lifts_to_branch():
    # A Lucene boolean on .exact lifts to a BranchFilter tree, same as .search
    # (#633 — live-verified: the decomposed form returns the identical 859).
    # Canonical column order too (NOT title_and_abstract.exact.search).
    oqo, vr = _parse_and_validate(
        {"search.title_and_abstract.exact": "Windows AND (DLL OR DLLs)"})
    assert vr.valid, [getattr(e, "message", e) for e in vr.errors]
    rows = oqo.to_dict()["filter_rows"]
    assert rows[0]["column_id"] == "title_and_abstract.search.exact"
    assert rows[0]["value"] == "Windows"
    assert rows[1]["join"] == "or"
    assert [f["value"] for f in rows[1]["filters"]] == ["DLL", "DLLs"]


@pytest.mark.parametrize("field", ["title", "abstract", "title_and_abstract"])
def test_exact_scoped_search_generalizes_across_scoped_fields(field):
    _, vr = _parse_and_validate({f"search.{field}.exact": "foo"})
    assert vr.valid, [getattr(e, "message", e) for e in vr.errors]


def test_plain_scoped_search_still_validates():
    _, vr = _parse_and_validate({"search.title_and_abstract": "cancer"})
    assert vr.valid, [getattr(e, "message", e) for e in vr.errors]


def test_comma_in_value_stays_one_clause_and_normalizes():
    # A raw comma in a search value is legal top-level (analyzer strips it) but
    # would render an x_query.url the API edge rejects (comma = clause
    # separator). It normalizes to a space — result-preserving, live-verified
    # (238,632 both forms) — and stays ONE clause.
    oqo, vr = _parse_and_validate({"search.title": "cancer, treatment"})
    assert vr.valid, [getattr(e, "message", e) for e in vr.errors]
    rows = oqo.to_dict()["filter_rows"]
    assert len(rows) == 1
    assert rows[0]["value"] == "cancer treatment"


def test_comma_inside_quotes_is_kept():
    # Quoted commas are literal phrase text; the engine's clause splitter is
    # quote-aware, so the rendered filter clause stays executable.
    oqo, _ = _parse_and_validate({"search.title": 'foo "bar, baz"'})
    rows = oqo.to_dict()["filter_rows"]
    assert rows[0]["value"] == 'foo "bar, baz"'


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


# --- the exact AND-of-words form (#633, surface per Jason) --------------------

def test_bare_multiword_exact_splits_to_per_token_leaves_and_renders_quoted_and():
    # Bare multi-word on .exact = no-stem AND-of-words — a different query from
    # the quoted phrase (live: title.search.exact:cancer treatment = 224,070
    # vs :"cancer treatment" = 36,755). Canonical OQO: one exact leaf PER TOKEN
    # (count-verified identical on prod); OQL surface: `has ("cancer" and
    # "treatment")` — no new grammar.
    oqo, vr = _parse_and_validate({"search.title.exact": "cancer treatment"})
    assert vr.valid, [getattr(e, "message", e) for e in vr.errors]
    rows = oqo.to_dict()["filter_rows"]
    assert [(r["column_id"], r["value"]) for r in rows] == [
        ("display_name.search.exact", "cancer"),
        ("display_name.search.exact", "treatment"),
    ]
    assert 'has ("cancer" and "treatment")' in render(oqo)


def test_wildcard_token_splits_and_renders():
    oqo, vr = _parse_and_validate({"search.title.exact": "cancer treat*"})
    assert vr.valid, [getattr(e, "message", e) for e in vr.errors]
    values = [r["value"] for r in oqo.to_dict()["filter_rows"]]
    assert values == ["cancer", "treat*"]
    assert 'has ("cancer" and "treat*")' in render(oqo)


def test_exact_boolean_lift_renders_faithful_oql():
    # The lifted boolean renders real OQL (was: lossy quoted phrase).
    oqo, _ = _parse_and_validate(
        {"search.title_and_abstract.exact": "Windows AND (DLL OR DLLs)"})
    oql = render(oqo)
    assert '"Windows"' in oql and '"DLL" or "DLLs"' in oql
    assert '"Windows AND (DLL OR DLLs)"' not in oql


def test_quoted_phrase_exact_still_renders_plain_quotes():
    oqo, _ = _parse_and_validate({"search.title.exact": '"cancer treatment"'})
    leaf = oqo.to_dict()["filter_rows"][0]
    assert leaf["value"] == '"cancer treatment"'
    assert 'has ("cancer treatment")' in render(oqo)
