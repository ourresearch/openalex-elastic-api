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
