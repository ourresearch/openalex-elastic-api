"""Annotate unresolvable entity IDs in the OQL render (oxjob #418).

A shape-valid OpenAlex ID the resolver can't find (deleted / merged-not-followed /
typo) used to render as a bare ID — indistinguishable from the resolverless case
(no resolver supplied → nothing looked up). When a resolver IS present and misses,
we now append a neutral `[no entity found]` annotation; when no resolver is
supplied we stay bare. The ID remains valid + queryable (display-only change), and
the `[...]` annotation is discarded on re-parse so round-trip is unaffected.

Pure: no app boot. Run with
    PYTHONPATH=. pytest tests/oql/test_unresolvable_id_render.py -q --noconftest
"""
import pytest

import tests.oql._qt_loader  # noqa: F401  (installs the pure query_translation stub)

from query_translation import oql_lang  # noqa: E402
from query_translation.oqo import OQO, LeafFilter  # noqa: E402
from query_translation.oql_parser import parse_oql_to_oqo  # noqa: E402


# Canonical works author-id column (OQL surface `author`); resolves_name=True.
_AUTHOR_COL = "authorships.author.id"
_MISS = lambda v, c=None: None          # resolver that always misses
_HIT = lambda v, c=None: "Jane Doe"     # resolver that always resolves


def _oqo(value="a9999999999", col=_AUTHOR_COL):
    return OQO(get_rows="works", filter_rows=[LeafFilter(col, value, "is")])


def test_resolver_miss_annotates_no_entity_found():
    out = oql_lang.render_tree(_oqo(), resolver=_MISS)[0]
    assert out == "works where author is a9999999999 [no entity found]"


def test_self_id_column_stays_bare_on_miss():
    # `ids.openalex` (the entity's own id) is NOT name-resolvable in production
    # (_RESOLVE_NAMESPACE maps it to None — entity-agnostic), so a resolver miss
    # there means "no name for this kind of column", NOT "entity not found". It
    # must stay bare, never `[no entity found]` (would lie for every real entity).
    oqo = OQO(get_rows="authors",
              filter_rows=[LeafFilter("ids.openalex", "A9999999999", "is")])
    out = oql_lang.render_tree(oqo, resolver=_MISS)[0]
    assert out == "authors where openalex id is A9999999999"
    assert "[" not in out


def test_no_resolver_stays_bare():
    # The whole subtlety: a resolverless render must NOT stamp [no entity found]
    # on every ID (nothing was looked up).
    out = oql_lang.render_tree(_oqo())[0]
    assert out == "works where author is a9999999999"
    assert "[" not in out


def test_resolver_hit_renders_name_unchanged():
    out = oql_lang.render_tree(_oqo(), resolver=_HIT)[0]
    assert out == "works where author is a9999999999 [Jane Doe]"


def test_string_render_matches_tree_render():
    # render() (string path) and render_tree() must agree (one source of truth).
    assert (
        oql_lang.render(_oqo(), resolver=_MISS)
        == oql_lang.render_tree(_oqo(), resolver=_MISS)[0]
    )


def test_round_trip_discards_annotation():
    rendered = oql_lang.render_tree(_oqo(), resolver=_MISS)[0]
    rt = parse_oql_to_oqo(rendered)
    bare = parse_oql_to_oqo("works where author is a9999999999")
    assert rt.to_dict() == bare.to_dict()


def test_multi_value_each_annotated():
    oqo = OQO(get_rows="works", filter_rows=[
        LeafFilter(_AUTHOR_COL, v, "is") for v in ("a5117578858", "a5128820475")
    ])
    out = oql_lang.render_tree(oqo, resolver=_MISS)[0]
    assert out.count("[no entity found]") == 2


@pytest.mark.parametrize("entity,column", [
    ("authors", "affiliations.institution.id"),
    ("locations", "source_id"),
    ("locations", "publisher"),
    ("awards", "funder.id"),
])
def test_wired_homonym_id_columns_are_name_resolvable(entity, column):
    # #418 follow-up: these entity-homonym ID columns carried resolves_name=True
    # but had no _RESOLVE_NAMESPACE entry, so they rendered bare in prod (the gate
    # kept them bare). Now wired to their entity namespace → a miss legitimately
    # annotates [no entity found] (and a hit would show the name).
    from query_translation.oql_lang import _column_resolves_name
    assert _column_resolves_name(column)
    oqo = OQO(get_rows=entity, filter_rows=[LeafFilter(column, "I999", "is")])
    assert oql_lang.render_tree(oqo, resolver=_MISS)[0].endswith("[no entity found]")


def test_value_segments_concatenate_to_value_with_name():
    # The documented contract: _value_segments must concatenate to exactly what
    # _value_with_name returns (here, the miss branch).
    fld = oql_lang._BY_COLUMN[_AUTHOR_COL]
    s = oql_lang._value_with_name(fld, "a9999999999", _AUTHOR_COL, _MISS)
    segs, _ = oql_lang._value_segments(fld, "a9999999999", _AUTHOR_COL, _MISS)
    assert "".join(seg.text for seg in segs) == s
    assert s == "a9999999999 [no entity found]"
