"""Scoped-search param fold: `search.<field>[.exact]=` → filter clause (oxjob #422).

The translation entrypoint folds top-level `search.<field>=<v>` query params into
filter clauses so the engine's scoped free-text search round-trips through OQO/OQL.
`search.<field>.exact=<v>` is the engine's *exact-phrase* scoped search; the fold must
emit the CANONICAL column order `<field>.search.exact` (which the url_parser normalizer
rewrites to a `<field>.search` column with a quoted, exact-phrase value), NOT the
malformed `<field>.exact.search` that the normalizer never strips and the registry
rejects as `invalid_column`.

Pure: no app boot (the fold + url_parser + validator import without Flask). Run with
    PYTHONPATH=. pytest tests/oql/test_scoped_search_fold.py -q --noconftest
"""
import pytest

import tests.oql._qt_loader  # noqa: F401  (installs the pure query_translation stub)

from query_translation.url_parser import (  # noqa: E402
    fold_scoped_search_params,
    parse_url_to_oqo,
)
from query_translation.validator import validate_oqo  # noqa: E402
from query_translation.oql_lang import render  # noqa: E402


def _fold_and_validate(params):
    """Fold scoped-search params, parse the resulting filter to OQO, validate."""
    folded = fold_scoped_search_params(dict(params))
    oqo = parse_url_to_oqo("works", filter_string=folded)
    return oqo, validate_oqo(oqo)


# --- the helper builds canonical column order --------------------------------

def test_exact_folds_to_canonical_search_exact():
    # `.exact` is pulled off, re-attached AFTER `.search` (canonical order).
    assert (
        fold_scoped_search_params({"search.title_and_abstract.exact": "foo"})
        == "title_and_abstract.search.exact:foo"
    )


def test_exact_never_emits_malformed_exact_search_order():
    out = fold_scoped_search_params({"search.title_and_abstract.exact": "foo"})
    assert ".exact.search" not in out  # the #422 bug: order must not regress


def test_plain_scoped_search_unchanged():
    assert (
        fold_scoped_search_params({"search.title_and_abstract": "foo"})
        == "title_and_abstract.search:foo"
    )


def test_no_scoped_params_leaves_filter_untouched():
    # None signals "no folding" so the caller leaves params['filter'] as-is.
    assert fold_scoped_search_params({"filter": "type:article"}) is None


def test_fold_joins_onto_existing_filter_with_bare_comma():
    assert (
        fold_scoped_search_params({"filter": "type:article", "search.title": "x"})
        == "type:article,title.search:x"
    )


# --- the folded clause validates + renders as an exact phrase ----------------

def test_exact_fold_validates_and_renders_exact_phrase():
    oqo, vr = _fold_and_validate({"search.title_and_abstract.exact": "Windows AND (DLL OR DLLs)"})
    assert vr.valid, [getattr(e, "message", e) for e in vr.errors]
    leaf = oqo.to_dict()["filter_rows"][0]
    # canonical column (NOT title_and_abstract.exact.search), exact-phrase value
    assert leaf["column_id"] == "title_and_abstract.search"
    assert leaf["value"] == '"Windows AND (DLL OR DLLs)"'
    assert "has near" in render(oqo)


@pytest.mark.parametrize("field", ["title", "abstract", "title_and_abstract"])
def test_exact_fold_generalizes_across_scoped_fields(field):
    _, vr = _fold_and_validate({f"search.{field}.exact": "foo"})
    assert vr.valid, [getattr(e, "message", e) for e in vr.errors]


def test_plain_scoped_search_still_validates():
    _, vr = _fold_and_validate({"search.title_and_abstract": "cancer"})
    assert vr.valid, [getattr(e, "message", e) for e in vr.errors]
