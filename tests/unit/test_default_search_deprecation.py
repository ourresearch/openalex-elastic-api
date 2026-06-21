"""oxjob #430 — deprecate `default.search`, mint honest `text.search`.

`default.search` was a per-entity footgun: on works it duplicated `fulltext.search`
(byte-identical); on non-works it was the only handle on the broad
name+alternates+description/keywords search (≠ display_name.search). It is now
demoted to an `alternate_key` (kept accepted forever) of the honest canonical:
`fulltext.search` (works) / `text.search` (non-works). These tests lock the
result-preserving rename + the catalog fold + the bare-`?search=` honest seeding.
"""

import pytest

NON_WORKS = ["authors", "sources", "institutions", "topics", "concepts", "funders"]


# --- result preservation: text.search builds the SAME ES query as default.search ---

@pytest.mark.parametrize("index", ["authors", "sources", "institutions", "topics", "concepts"])
def test_text_search_query_identical_to_default_search(index):
    """On every non-works entity, `text.search` and `default.search` build the
    byte-identical ES query (both route through full_search_query on that index),
    so demoting default.search → alternate_of text.search changes no results."""
    from core.fields import SearchField

    def built(param):
        f = SearchField(param=param, index=index)
        f.value = "national"
        return f.build_query().to_dict()

    assert built("text.search") == built("default.search")


def test_works_default_search_identical_to_fulltext():
    """works `default.search` ≡ `fulltext.search` (the works demotion target)."""
    from core.fields import SearchField

    def built(param):
        f = SearchField(param=param, index="works")
        f.value = "machine learning"
        return f.build_query().to_dict()

    assert built("default.search") == built("fulltext.search")


# --- catalog fold: default.search demoted, text.search canonical & honest ---

def test_catalog_folds_default_search_into_canonical():
    # _merged_properties is the PUBLIC catalog (drops alternate_of aliases);
    # get_entity_properties is the internal dict that retains them so they resolve.
    from core.properties import _merged_properties
    from core.display_names import resolve_display_name

    for ent in NON_WORKS:
        public = _merged_properties(ent)
        assert "default.search" not in public, f"{ent}: default.search still in public catalog"
        text = public["text.search"]
        assert "default.search" in text.alternate_keys, f"{ent}: missing alt key"
        # honest label — NOT "name" (broad search also covers descriptions/keywords)
        dn, _ = resolve_display_name(ent, "text.search")
        assert dn == "text"

    works = _merged_properties("works")
    assert "default.search" not in works
    assert "default.search" in works["fulltext.search"].alternate_keys
    assert "default.search.exact" in works["fulltext.search.exact"].alternate_keys


def test_default_search_still_resolves_as_alternate_key():
    """Demoted, NOT removed — it must keep resolving for the filter API / OQO."""
    from core.properties import get_property

    # ENTITY_PROPERTIES retains aliases so they still resolve.
    assert get_property("authors", "default.search") is not None
    assert get_property("works", "default.search") is not None


# --- bare ?search= seeds the honest column (fixes #363 finding-#8 at the source) ---

def test_bare_search_seeds_honest_column():
    from query_translation.url_parser import parse_url_to_oqo

    def first_col(ent):
        oqo = parse_url_to_oqo(entity_type=ent, search_string="national")
        d = oqo.to_dict() if hasattr(oqo, "to_dict") else oqo
        return d["filter_rows"][0]["column_id"]

    assert first_col("works") == "fulltext.search"
    for ent in NON_WORKS:
        assert first_col(ent) == "text.search", ent


def test_oql_renders_text_not_full_text_on_non_works():
    """The finding-#8 break: a non-works bare search must render the `text` word,
    not the nonsensical `full text`."""
    from query_translation.url_parser import parse_url_to_oqo
    from query_translation.oql_lang import render

    # #363 decision 27/29 renamed the search operator `contains` → `has`.
    assert "text has" in render(parse_url_to_oqo(entity_type="authors", search_string="x"))
    assert "full text has" in render(parse_url_to_oqo(entity_type="works", search_string="x"))


# --- relevance registration (the post-deploy gap, 2026-06-21) ---
# The original ship checked the build_query *clause* but not whether `text.search`
# was registered as a "search query" — the flag that turns on relevance scoring
# and makes `sort=relevance_score` legal. It was missing from check_is_search_query
# (and the two semantic-exclusion lists), so live `text.search` matched the right
# docs but came back relevance_score=None, ordered by the entity default (works_count)
# instead of relevance, and `sort=relevance_score:desc` 400'd. Lock it here.

def test_text_search_counts_as_a_search_query():
    """`text.search` must enable relevance scoring/sorting, exactly like the
    `default.search` it replaces (else non-works search loses relevance ranking)."""
    from core.search import check_is_search_query

    assert check_is_search_query([{"text.search": "patients"}], None) is True
    # parity with the key it supersedes
    assert check_is_search_query([{"default.search": "patients"}], None) is True


def test_text_search_in_semantic_exclusion_lists():
    """`text.search` is a free-text search op, so it must be incompatible with
    semantic search just like every other `*.search` key (consistency guard)."""
    from core.shared_view import SEARCH_FILTER_KEYS
    from core.vector_index import _SEARCH_FILTER_KEYS

    assert "text.search" in SEARCH_FILTER_KEYS
    assert "text.search" in _SEARCH_FILTER_KEYS
