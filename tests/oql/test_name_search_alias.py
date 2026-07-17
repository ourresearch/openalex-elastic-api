"""`name` = the name-search word on every NON-works entity (#611 follow-up).

Jason (2026-07-17): `authors where name has (einstein)` must work — and the same
on every other non-works entity — while works keeps its curated "title" word and
does NOT accept `name`. Mechanics:

  * registry: `display_name.search` carries the input alias 'name' on all
    non-works entities (a GLOBAL_DISPLAY_NAME_OVERRIDES entry + the five
    per-entity overrides that shadow it) — properties catalog 7.2.0, MINOR.
  * parse: `_build_entity_fallback` surfaces non-works SEARCH columns from the
    registry (display_name + aliases + cid), with canonical-self columns
    claiming contested words before alias-columns (so `name` lands on
    display_name.search, not on default.search → text.search).
  * render: `_oql_field` is entity-aware for search columns via _RENDER_ENTITY
    (set for `_build_tree`'s extent) + `_entity_search_word`, preferring the
    BASE column's registry label ('name') when it safely round-trips.

    PYTHONPATH=. pytest tests/oql/test_name_search_alias.py -q
"""
import pytest

from query_translation import oql_lang as L

# Every non-works entity with a display_name.search column gets the word.
# (`types` — OQL's spelling for work-types — is absent: its parser entity string
# doesn't resolve in the properties registry, a PRE-existing gap that breaks ALL
# registry-fallback fields there, not just `name`.)
NAME_ENTITIES = [
    "authors", "institutions", "sources", "publishers", "funders",
    "topics", "keywords", "concepts", "domains", "fields", "subfields",
    "countries", "continents", "languages", "licenses", "sdgs",
    "source-types", "institution-types", "awards", "oa-statuses",
]


@pytest.mark.parametrize("entity", NAME_ENTITIES)
def test_name_parses_to_display_name_search(entity):
    oqo = L.parse(f"{entity} where name has (einstein)")
    assert [(f.column_id, f.value) for f in oqo.filter_rows] == [
        ("display_name.search", "einstein")
    ]


@pytest.mark.parametrize("entity", ["authors", "institutions", "topics", "awards", "oa-statuses"])
def test_name_is_the_canonical_render_word(entity):
    oqo = L.parse(f"{entity} where name has (einstein)")
    assert L.render(oqo) == f"{entity} where name has (einstein)"


@pytest.mark.parametrize("entity", ["authors", "sources", "keywords"])
def test_name_round_trips(entity):
    oqo = L.parse(f"{entity} where name has (einstein)")
    assert L.parse(L.render(oqo)).filter_rows == oqo.filter_rows


def test_works_does_not_accept_name():
    with pytest.raises(Exception) as exc:
        L.parse("works where name has (foo)")
    assert "unknown field" in str(exc.value)


def test_works_title_render_unchanged():
    oqo = L.parse("works where title has (ai)")
    assert [f.column_id for f in oqo.filter_rows] == ["display_name.search"]
    assert L.render(oqo) == "works where title has (ai)"


def test_authors_title_now_renders_as_name():
    # "title" stays a parse alias on non-works (back-compat for old URLs), but
    # the canonical word there is now "name" — the pre-#611 render of
    # `authors where title has (…)` read as a works-ism.
    oqo = L.parse("authors where title has (einstein)")
    assert [f.column_id for f in oqo.filter_rows] == ["display_name.search"]
    assert L.render(oqo) == "authors where name has (einstein)"


def test_text_broad_search_unchanged():
    # `text` (the #430 broad non-works search) must not be captured by `name`.
    oqo = L.parse("authors where text has (einstein)")
    assert [f.column_id for f in oqo.filter_rows] == ["text.search"]
    assert L.render(oqo) == "authors where text has (einstein)"
