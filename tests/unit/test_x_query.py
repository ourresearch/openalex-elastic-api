"""Unit tests for the `meta.x_query` echo on the legacy entity path (oxjob #378 S1).

S1 makes the server emit the private `meta.x_query` triple {oql, oqo, url} on every
entity response (not just the OQL/OQO execute path of #373), so the GUI can source
its chip state from the server's canonical query object instead of re-parsing the
route. These tests cover the three moving parts, all offline (no ES):

  - `build_x_query`            — the shared triple builder (moved to its own module)
  - `attach_x_query`           — the best-effort injector in core.shared_view
  - MetaSchema `x_query` field — the pass-through that lets it survive marshmallow dump
"""

import pytest

from core.shared_view import attach_x_query
from query_translation.url_parser import parse_url_to_oqo
from query_translation.x_query import build_x_query
from works.schemas import MessageSchema


class _Args:
    """Minimal stand-in for werkzeug's request.args (supports get(key, type=))."""

    def __init__(self, d):
        self._d = d

    def get(self, key, type=None, default=None):
        value = self._d.get(key, default)
        if value is not None and type is not None:
            try:
                return type(value)
            except (TypeError, ValueError):
                return default
        return value


class _Req:
    def __init__(self, d):
        self.args = _Args(d)


# --------------------------------------------------------------------------- #
# build_x_query
# --------------------------------------------------------------------------- #

def test_build_x_query_flat_query_has_url_and_triple():
    oqo = parse_url_to_oqo(
        entity_type="works",
        filter_string="type:article,publication_year:2020-",
        sort_string="cited_by_count:desc",
    )
    xq = build_x_query(oqo)

    assert set(xq) == {"oql", "oqo", "url"}
    # A query that arrived as a URL is URL-expressible, so `url` is never None here.
    assert xq["url"] is not None
    assert xq["url"].startswith("/works?filter=")
    assert xq["oqo"]["get_rows"] == "works"
    assert isinstance(xq["oql"], str) and xq["oql"]


def test_build_x_query_no_resolver_renders_bare_ids():
    """The hot path passes no entity_resolver, so OQL keeps bare IDs (no ES lookups)."""
    oqo = parse_url_to_oqo(
        entity_type="works", filter_string="authorships.institutions.id:I136199984"
    )
    xq = build_x_query(oqo)  # entity_resolver defaults to None
    assert "I136199984" in xq["oql"]
    assert "[" not in xq["oql"]  # no `[Harvard]`-style display-name annotation


def test_build_x_query_no_resolver_never_stamps_no_entity_found():
    """oxjob #363: `authorships.institutions.lineage` (what `institution is`
    canonically maps to) IS name-resolvable, so the engine's #418 miss-annotation
    gate applies to it — unlike the `.id` column above, which dodges the gate.
    A resolverless build must render it bare, never `[no entity found]` (Harvard
    exists; nothing was looked up). This was live-broken on both executed-query
    paths (`/?oql=` execute + per-entity SERP) until the resolver=None fix."""
    oqo = parse_url_to_oqo(
        entity_type="works",
        filter_string="authorships.institutions.lineage:I136199984",
    )
    xq = build_x_query(oqo)
    assert xq["oql"] == "works where institution is (I136199984)"
    assert "[no entity found]" not in xq["oql"]


def test_build_x_query_no_resolver_skips_builtin_name_tables():
    """Decision 14: executed-path canonical OQL is fully bare — not even the
    local config/*.yaml builtin names (`country is US [United States]`)."""
    oqo = parse_url_to_oqo(entity_type="works", filter_string="authorships.countries:US")
    xq = build_x_query(oqo)
    assert xq["oql"] == "works where country is (US)"


def test_build_x_query_with_resolver_annotates_hits_and_misses():
    """A supplied entity_resolver keeps the display-service behavior: hits get
    `[name]`, genuine misses on a resolvable column get `[no entity found]`."""
    names = {"institutions/I136199984": "Harvard University"}
    oqo = parse_url_to_oqo(
        entity_type="works",
        filter_string="authorships.institutions.lineage:I136199984|I9999999999",
    )
    xq = build_x_query(oqo, entity_resolver=names.get)
    assert "[Harvard University]" in xq["oql"]
    assert "[no entity found]" in xq["oql"]


# --------------------------------------------------------------------------- #
# safe_get_display_name — keyword namespace resolution (oxjob #428)
# --------------------------------------------------------------------------- #


def test_safe_get_display_name_resolves_keyword_via_keyword_index(monkeypatch):
    """Keywords have slug-based, path-namespaced ids (keywords/<slug>) that the
    letter+digit-only get_display_name can't resolve — they rendered as
    `[no entity found]` on valid filters. safe_get_display_name routes them to the
    keywords index, keyed by the full openalex URL it stores."""
    from query_translation import x_query

    captured = {}

    def fake_lookup(ids, connection="default"):
        captured["ids"] = ids
        return {"https://openalex.org/keywords/anticoagulant": "Anticoagulant"}

    monkeypatch.setattr(
        "core.group_by.display_names.get_display_names_keywords_licenses_topics",
        fake_lookup,
    )
    assert x_query.safe_get_display_name("keywords/anticoagulant") == "Anticoagulant"
    # routed by the FULL url the keywords index stores, not the bare slug
    assert captured["ids"] == ["https://openalex.org/keywords/anticoagulant"]


def test_safe_get_display_name_keyword_miss_returns_none(monkeypatch):
    """An unresolvable keyword still yields None (-> `[no entity found]`)."""
    from query_translation import x_query

    monkeypatch.setattr(
        "core.group_by.display_names.get_display_names_keywords_licenses_topics",
        lambda ids, connection="default": {},
    )
    assert x_query.safe_get_display_name("keywords/not-a-real-keyword") is None


# --------------------------------------------------------------------------- #
# attach_x_query  (core.shared_view)
# --------------------------------------------------------------------------- #

def test_attach_x_query_injects_into_meta():
    result = {"meta": {"count": 5}, "results": []}
    attach_x_query(result, _Req({"filter": "is_oa:true", "sort": "cited_by_count:desc"}),
                   "works-v33")
    assert "x_query" in result["meta"]
    assert result["meta"]["x_query"]["url"] == "/works?filter=is_oa:true&sort=cited_by_count:desc"


def test_attach_x_query_uses_raw_args_not_injected_defaults():
    """x_query must mirror the user's query, so an empty filter yields no filter
    component even though the legacy path would inject e.g. is_xpac:false into
    params (which attach_x_query deliberately does not read)."""
    result = {"meta": {"count": 1}, "results": []}
    attach_x_query(result, _Req({}), "works-v33")
    assert "is_xpac" not in (result["meta"]["x_query"]["url"] or "")


def test_attach_x_query_entity_type_derived_from_index():
    result = {"meta": {"count": 1}, "results": []}
    attach_x_query(result, _Req({"filter": "works_count:>100"}), "authors-v19")
    assert result["meta"]["x_query"]["oqo"]["get_rows"] == "authors"
    assert result["meta"]["x_query"]["url"].startswith("/authors")


def test_attach_x_query_noop_without_meta():
    result = {"results": []}
    attach_x_query(result, _Req({"filter": "is_oa:true"}), "works-v33")
    assert "meta" not in result  # untouched, no crash


def test_attach_x_query_is_best_effort_on_error():
    """A non-dict result must never raise — x_query is additive metadata."""
    attach_x_query(None, _Req({"filter": "is_oa:true"}), "works-v33")  # no exception


def test_attach_x_query_threads_scoped_search():
    """The scoped-search family must survive into ALL THREE echo forms (#633 —
    before this a scoped search echoed as bare `works`, a whole-corpus silent
    mis-scope for chips/exports)."""
    # A multi-word value on an .exact param canonicalizes to one leaf PER TOKEN
    # (no-stem AND-of-words, #633) — so those expect two rows of the column.
    expected = {
        "search.title": ["display_name.search"],
        "search.title.exact": ["display_name.search.exact"] * 2,
        "search.title_and_abstract": ["title_and_abstract.search"],
        "search.title_and_abstract.exact": ["title_and_abstract.search.exact"] * 2,
        "search.exact": ["fulltext.search.exact"] * 2,
    }
    for param, columns in expected.items():
        result = {"meta": {"count": 5}, "results": []}
        attach_x_query(result, _Req({param: "dark matter"}), "works-v33")
        xq = result["meta"]["x_query"]
        cols = [f.get("column_id") for f in xq["oqo"].get("filter_rows", [])]
        assert cols == columns, f"{param}: {cols}"
        assert xq["url"] and columns[0] in xq["url"], f"{param}: {xq['url']}"
        assert xq["oql"] != "works", f"{param} echoed bare works"


def test_attach_x_query_scoped_search_ands_with_plain_search_and_filter():
    """Multiple simultaneous search params AND together (engine:
    _extract_all_search_params) alongside a filter."""
    result = {"meta": {"count": 5}, "results": []}
    attach_x_query(result, _Req({
        "search": "brain",
        "search.title_and_abstract": "dark matter",
        "filter": "type:article",
    }), "works-v33")
    cols = {f.get("column_id")
            for f in result["meta"]["x_query"]["oqo"]["filter_rows"]}
    assert cols == {"fulltext.search", "title_and_abstract.search", "type"}


def test_attach_x_query_bare_multiword_exact_value_is_and_of_words():
    """A bare multi-word `.exact` value is no-stem AND-of-words — count-distinct
    from the quoted phrase (live: 224,070 vs 36,755) — so the echo must NOT
    quote it into a phrase (#633 reversed the #568 auto-quote). Canonical form:
    one exact leaf per token; OQL `has ("cancer" and "treatment")` (per Jason);
    URL = ANDed per-token clauses (prod count-verified ≡ the original)."""
    result = {"meta": {"count": 5}, "results": []}
    attach_x_query(result, _Req({"search.title.exact": "cancer treatment"}),
                   "works-v33")
    xq = result["meta"]["x_query"]
    values = [f["value"] for f in xq["oqo"]["filter_rows"]]
    assert values == ["cancer", "treatment"]
    assert "display_name.search.exact:cancer,display_name.search.exact:treatment" in xq["url"]
    assert 'has ("cancer" and "treatment")' in xq["oql"]


# --------------------------------------------------------------------------- #
# MetaSchema pass-through (survives marshmallow dump)
# --------------------------------------------------------------------------- #

def test_meta_schema_passes_x_query_through_dump():
    ms = MessageSchema()
    dumped = ms.dump({
        "meta": {"count": 3, "x_query": {"oql": "works where ...",
                                          "oqo": {"get_rows": "works"},
                                          "url": "/works?filter=is_oa:true"}},
        "results": [],
        "group_by": [],
    })
    assert dumped["meta"]["x_query"]["url"] == "/works?filter=is_oa:true"


def test_meta_schema_omits_x_query_when_absent():
    ms = MessageSchema()
    dumped = ms.dump({"meta": {"count": 3}, "results": [], "group_by": []})
    assert "x_query" not in dumped["meta"]
