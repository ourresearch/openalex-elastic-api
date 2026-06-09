"""Fixes from Jason's random-search walkthrough batch 2 (oxjob #363, discovery run #3).

Cases 4-8:

  4. `citation_normalized_percentile.value` is a curated num field
     (`citation percentile by subfield`); the raw column id still parses.
  5. fields / subfields / domains / languages resolve a `[display name]` from
     config/*.yaml (path-style + code IDs ES can't route): `field is 27 [Medicine]`,
     `language is en [English]`.
  6. `open_access.any_repository_has_fulltext` renders a friendly boolean phrasing
     (`it has fulltext in a repository`) that round-trips.
  7. `cited_by` / `cites` are curated id fields ("cited by" / "cites") that resolve
     the referenced work's title; every `[display name]` annotation is truncated to
     a uniform length with an ellipsis.
  8a. A quoted search phrase inside a boolean group keeps its quotes through a
     URL -> OQO -> OQL render (was stripped -> invalid un-reparseable OQL).
  8b. Bare multi-word atoms mixed with `or` in a group are a hard ambiguity error
     (OQL never guesses operator precedence).

Run with:
    PYTHONPATH=. pytest tests/oql/test_search_walkthrough_3.py -q
"""
import re

import pytest

import tests.oql._qt_loader  # noqa: F401  (installs the pure query_translation stub)

from query_translation.oql_lang import (  # noqa: E402
    parse, render, render_tree, OQLError, _truncate_name, _NAME_ANNOTATION_MAX,
)
from query_translation.oqo_canonicalizer import canonicalize_oqo  # noqa: E402
from query_translation.url_parser import parse_url_to_oqo  # noqa: E402
from query_translation.oql_renderer import make_engine_resolver  # noqa: E402


def _render(oql, resolver=None):
    return render_tree(canonicalize_oqo(parse(oql)), resolver=resolver)[0]


def _leaves(oql):
    return canonicalize_oqo(parse(oql)).to_dict()["filter_rows"]


def _roundtrips(oql):
    """render(parse(oql)) re-parses without error."""
    parse(_render(oql))
    return True


# --------------------------------------------------------------------------- #
# Case 4 — citation_normalized_percentile.value
# --------------------------------------------------------------------------- #
def test_case4_citation_percentile_curated():
    assert _leaves("works where citation percentile by subfield is 99") == [
        {"column_id": "citation_normalized_percentile.value", "value": 99}]


# (oxjob #406 burned the raw-id "bridge" for this curated-but-not-GUI-faceted
# column — the clean OQL spec surfaces the friendly word only. The old
# `test_case4_raw_column_still_parses` asserted that burned bridge and was removed;
# a future `supported_by: oql` registry annotation will re-cover the raw id —
# tracked in the spin-out job `registry-supported-by-annotation`.)


def test_case4_render_word_round_trips():
    out = _render("works where citation percentile by subfield is 99")
    assert "citation percentile by subfield is 99" in out
    assert _roundtrips(out)


# --------------------------------------------------------------------------- #
# Case 5 — config-yaml value display names (the path/code entities)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("oql,annotation", [
    ("works where field is 27", "[Medicine]"),
    ("works where subfield is 3312", "[Sociology and Political Science]"),
    ("works where domain is 3", "[Physical Sciences]"),
    ("works where language is en", "[English]"),
])
def test_case5_config_yaml_display_names(oql, annotation):
    # entity_resolver=None -> the renderer falls back to the config/*.yaml tables.
    out = _render(oql, resolver=make_engine_resolver(None))
    assert annotation in out


def test_case5_field_resolution_round_trips():
    out = _render("works where field is 27", resolver=make_engine_resolver(None))
    assert _roundtrips(out)  # the [Medicine] annotation is an ignorable comment


def test_case5_language_resolves_name():
    from query_translation.oql_lang import _ALIAS
    assert _ALIAS["language"].resolves_name is True


# --------------------------------------------------------------------------- #
# Case 6 — friendly boolean phrasing for any_repository_has_fulltext
# --------------------------------------------------------------------------- #
def test_case6_repository_fulltext_phrasing_round_trips():
    out = _render("works where open_access.any_repository_has_fulltext is true")
    assert out == "works where it has fulltext in a repository"
    assert _leaves(out) == [
        {"column_id": "open_access.any_repository_has_fulltext", "value": True}]


def test_case6_negated_phrasing():
    out = _render("works where open_access.any_repository_has_fulltext is false")
    assert out == "works where it doesn't have fulltext in a repository"


# --------------------------------------------------------------------------- #
# Case 7 — cited_by / cites + uniform name truncation
# --------------------------------------------------------------------------- #
def test_case7_cited_by_render_word():
    assert _render("works where cited_by is w1984893742") == "works where cited by is w1984893742"


def test_case7_cites_render_word():
    assert _render("works where cites is w1984893742") == "works where cites is w1984893742"


def _work_title_resolver():
    long = ("Reduced Order Modeling of Turbulent Flows via Deep Learning "
            "Surrogates and Real-Time State Estimation")

    def es(key):
        return long if key.startswith("works/") else None

    return make_engine_resolver(es), long


def test_case7_resolves_work_title_truncated():
    resolver, long = _work_title_resolver()
    out = _render("works where cited_by is w1984893742", resolver=resolver)
    m = re.search(r"\[(.*?)\]", out)
    assert m, out
    shown = m.group(1)
    assert len(shown) == _NAME_ANNOTATION_MAX           # clipped to the uniform max
    assert shown.endswith("…") and shown[:-1] in long   # ellipsis + a real prefix
    assert _roundtrips("works where cited_by is w1984893742")


def test_truncate_helper():
    assert _truncate_name("short name") == "short name"
    long = "x" * 100
    assert len(_truncate_name(long)) == _NAME_ANNOTATION_MAX
    assert _truncate_name(long).endswith("…")
    # internal whitespace collapses
    assert _truncate_name("a   b\n c") == "a b c"


# --------------------------------------------------------------------------- #
# Case 8a — quoted phrases inside a boolean group keep their quotes
# --------------------------------------------------------------------------- #
def test_case8a_group_phrase_keeps_quotes_and_round_trips():
    oqo = parse_url_to_oqo(
        "works", search_string='("reduced order model" OR "surrogate model")')
    out = render_tree(canonicalize_oqo(oqo))[0]
    # each phrase keeps its quotes -> renders as a phrase (near "..."), not a bare
    # multi-word bag that would re-parse as ambiguous AND/OR
    assert 'near "reduced order model"' in out
    assert 'near "surrogate model"' in out
    parse(out)  # the headline guarantee: the rendered OQL re-parses


def test_case8a_standalone_phrase_unchanged():
    oqo = parse_url_to_oqo("works", search_string='"reduced order model"')
    leaf = oqo.to_dict()["filter_rows"][0]
    assert leaf["value"] == '"reduced order model"'  # quotes retained


# --------------------------------------------------------------------------- #
# Case 8b — bare multi-word + or is a hard ambiguity error (no precedence guess)
# --------------------------------------------------------------------------- #
def test_case8b_bare_multiword_or_is_ambiguous():
    with pytest.raises(OQLError) as exc:
        parse("works where full text contains (reduced order model or surrogate model)")
    assert "ambiguous" in str(exc.value).lower()


# --------------------------------------------------------------------------- #
# #399 follow-up — a plain multi-word search VALUE renders parenthesized.
# A bare `default.search:a b` URL (one leaf, multi-word value) used to render
# `... contains a b` (no delimiter) -> OQL_UNDELIMITED_TERM_LIST on re-parse.
# Post-#399 the engine runs plain multi-word as cross-field AND, which is exactly
# `contains (a b)`, so the renderer must parenthesize. (oxjob #363)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("filter_string", [
    "default.search:cenizas volcánicas",
    "title.search:foo bar baz",
    "abstract.search:machine learning models",
])
def test_multiword_search_value_renders_parenthesized_and_reparses(filter_string):
    out = render_tree(canonicalize_oqo(parse_url_to_oqo("works", filter_string=filter_string)))[0]
    # parenthesized, not a bare undelimited term list
    assert " contains (" in out, out
    parse(out)  # the headline guarantee: the rendered OQL re-parses


def test_singleword_search_value_stays_bare():
    # a single stemmed term must NOT gain parens (regression guard on the fix)
    out = render_tree(canonicalize_oqo(parse_url_to_oqo("works", filter_string="title.search:single")))[0]
    assert "contains single" in out and "(" not in out, out
    parse(out)
