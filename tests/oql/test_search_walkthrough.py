"""Fixes surfaced by Jason's random-search walkthrough (oxjob #363, discovery run #2).

Four behaviors locked here:

  1. Case 1 — the entity head shares the `where` line when a query wraps
     (`works where institution is …`, not `works` alone on line 1).
  2. Case 2.1 — curly/smart double-quotes are coerced to ASCII and a run of 2+
     double-quotes collapses to one (a triple-quoted phrase -> a single-quoted
     one), on BOTH the OQL parse surface and the URL value surface (so a
     triple-quoted oxurl round-trips).
  3. Case 2.2 — a lone `sort by relevance_score desc` is dropped from the
     canonical form when the query has a search clause (it's the implicit
     default there); kept otherwise.
  4. Case 3.3 — every works-registry column_id is accepted as an OQL input alias
     even with no curated friendly name (renders back as the raw id, round-trips);
     a genuinely-unknown field still errors; search columns are excluded.

Run with:
    PYTHONPATH=. pytest tests/oql/test_search_walkthrough.py -q
"""
import pytest

import tests.oql._qt_loader  # noqa: F401  (installs the pure query_translation stub)

from query_translation.oql_lang import (  # noqa: E402
    parse, render, render_tree, OQLError, _registry_fallback_field,
)
from query_translation.oqo_canonicalizer import canonicalize_oqo  # noqa: E402
from query_translation.url_parser import parse_url_to_oqo  # noqa: E402


def _render(oql):
    return render_tree(canonicalize_oqo(parse(oql)))[0]


def _leaves(oql):
    return canonicalize_oqo(parse(oql)).to_dict()["filter_rows"]


# --------------------------------------------------------------------------- #
# Case 1 — entity head on the same line as `where`
# --------------------------------------------------------------------------- #
def test_case1_entity_head_joins_where_line():
    out = _render(
        "works where institution is i1295562517 and source is not s4306400562 "
        "and source is s4210230483")
    lines = out.split("\n")
    # multi-line (the implicit-AND body explodes, decision 32 revert) but line 1
    # keeps `works where` on the same line as the first clause — not a bare
    # "works".
    assert len(lines) > 1
    assert lines[0] == "works where institution is i1295562517"
    assert lines[1].lstrip().startswith("and source is")


def test_case1_short_query_stays_flat():
    assert _render("works where type is article") == "works where type is article"


# --------------------------------------------------------------------------- #
# Case 2.1 — curly + multi-quote coercion
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("src", [
    'works where title has """hello world"""',
    'works where title has “hello world”',          # curly
    'works where title has “““hello world”””',      # curly + triple
])
def test_case2_1_weird_quotes_coerce_to_single(src):
    assert _render(src) == 'works where title has "hello world"'


def test_case2_1_url_triple_quote_roundtrips():
    oqo = parse_url_to_oqo(
        "works",
        filter_string='raw_affiliation_strings.search:"""universiteit maastricht"""')
    # OQO carries the clean single-quoted value, not the triple-quoted one
    leaf = oqo.to_dict()["filter_rows"][0]
    assert leaf["value"] == '"universiteit maastricht"'
    # and the rendered OQL re-parses (the bug: it didn't, before #363)
    rendered = render_tree(canonicalize_oqo(oqo))[0]
    reparsed = canonicalize_oqo(parse(rendered)).to_dict()["filter_rows"]
    assert reparsed == canonicalize_oqo(oqo).to_dict()["filter_rows"]


# --------------------------------------------------------------------------- #
# Case 2.2 — drop the redundant default relevance sort
# --------------------------------------------------------------------------- #
def _sort(url_kw):
    oqo = parse_url_to_oqo("works", **url_kw)
    return canonicalize_oqo(oqo).to_dict().get("sort_by")


def test_case2_2_relevance_sort_dropped_for_search():
    assert _sort(dict(filter_string="title.search:climate",
                      sort_string="relevance_score:desc")) in (None, [])


def test_case2_2_relevance_sort_kept_without_search():
    s = _sort(dict(filter_string="type:article", sort_string="relevance_score:desc"))
    assert s and s[0]["column_id"] == "relevance_score"


def test_case2_2_relevance_asc_kept():
    s = _sort(dict(filter_string="title.search:climate", sort_string="relevance_score:asc"))
    assert s and s[0]["direction"] == "asc"


def test_case2_2_non_relevance_sort_kept():
    s = _sort(dict(filter_string="title.search:climate", sort_string="cited_by_count:desc"))
    assert s and s[0]["column_id"] == "cited_by_count"


def test_case2_2_relevance_with_secondary_key_kept():
    s = _sort(dict(filter_string="title.search:climate",
                   sort_string="relevance_score:desc,publication_date:desc"))
    assert s and len(s) == 2


# --------------------------------------------------------------------------- #
# Case 3.1/3.2 — subfield is registered + name-resolved
# --------------------------------------------------------------------------- #
def test_case3_subfield_parses_and_renders():
    assert _leaves("works where subfield is 2712") == [
        {"column_id": "primary_topic.subfield.id", "value": "2712"}]


def test_case3_subfield_value_name_resolves():
    oqo = parse("works where subfield is 2712")
    out = render(oqo, resolver=lambda v, c=None: "Bioengineering"
                 if v == "2712" else None)
    assert out == "works where subfield is 2712 [Bioengineering]"


# --------------------------------------------------------------------------- #
# Case 3.3 — raw registry column ids accepted as input aliases
# --------------------------------------------------------------------------- #
_HAS_REGISTRY = _registry_fallback_field("ids.pmid") is not None
_needs_registry = pytest.mark.skipif(
    not _HAS_REGISTRY,
    reason="engine properties registry unavailable in this context")


@_needs_registry
@pytest.mark.parametrize("oql,expect", [
    ("works where ids.pmid is 12345678",
     [{"column_id": "ids.pmid", "value": "12345678"}]),
    ("works where biblio.volume is 42",
     [{"column_id": "biblio.volume", "value": "42"}]),
    ("works where authorships.institutions.country_code is us",
     [{"column_id": "authorships.institutions.country_code", "value": "us"}]),
])
def test_case3_3_raw_string_columns_accepted(oql, expect):
    assert _leaves(oql) == expect


@_needs_registry
def test_case3_3_raw_numeric_column_supports_comparison():
    assert _leaves("works where apc_paid.value_usd > 1000") == [
        {"column_id": "apc_paid.value_usd", "value": 1000, "operator": ">"}]


@_needs_registry
def test_case3_3_raw_key_round_trips():
    # A raw registry column id is accepted as input and round-trips to the same OQO.
    # `ids.pmid` has since gained a curated friendly word ("PMID", #381/#402), so the
    # render NORMALIZES the raw spelling to that word (and "PMID" re-parses to ids.pmid).
    # oxjob #406 dropped the redundant raw-id `_FIELDS` alias — the registry fallback
    # now parses the raw key — which is what un-masked this previously-skipped test
    # (its `_HAS_REGISTRY` probe keyed on ids.pmid, which used to sit in `_ALIAS`).
    out = _render("works where ids.pmid is 12345678")
    assert out == "works where PMID is 12345678"
    assert _leaves(out) == [{"column_id": "ids.pmid", "value": "12345678"}]


def test_case3_3_genuinely_unknown_field_still_errors():
    with pytest.raises(OQLError):
        parse("works where totally_made_up_field is 5")


@_needs_registry
@pytest.mark.parametrize("col", [
    "best_oa_location.raw_type",        # internal raw field
    "has_embeddings",                   # internal boolean
    "institution_assertions.id",        # not GUI-faceted / documented
    "cited_by_percentile_year.max",     # internal percentile field
])
def test_case3_3_internal_columns_excluded(col):
    # scope = GUI/docs parity (Jason): a real registry column that is NEITHER
    # GUI-faceted NOR documented is NOT accepted as a raw input alias.
    with pytest.raises(OQLError):
        parse(f"works where {col} is x")


@_needs_registry
def test_case3_3_search_columns_excluded():
    # search columns are mode-encoded (use the curated fields + quoting); their
    # raw .search.exact key is NOT accepted as an input alias.
    with pytest.raises(OQLError):
        parse('works where abstract.search.exact has "x"')


# --------------------------------------------------------------------------- #
# #397 — every GUI scope-alias `*.search` param resolves in OQL (cross-surface
# coherence: a shared "Title"/"Title & abstract"/etc. URL must validate in the
# editor, not error `unknown field "<param>.search"`).
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("param,column", [
    ("title.search", "display_name.search.exact"),              # #397 — the alias this job adds
    ("display_name.search", "display_name.search.exact"),
    ("title_and_abstract.search", "title_and_abstract.search.exact"),  # fixed upstream (#363)
    ("default.search", "fulltext.search.exact"),                # deprecated -> fulltext (#374)
    ("fulltext.search", "fulltext.search.exact"),
])
def test_397_gui_scope_search_aliases_resolve(param, column):
    assert _leaves(f'works where {param} has "x"') == [
        {"column_id": column, "value": "x", "operator": "has"}]
