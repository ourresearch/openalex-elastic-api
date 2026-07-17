"""Two #611 follow-up fixes (Jason 2026-07-17).

1. The `types` entity (OQL/OQO spelling of the catalog's `work-types`) now
   resolves registry-fallback fields. The alias map moved to
   `core.properties.ENTITY_KEY_ALIASES` and the getters
   (get_entity_properties / get_property / canonicalize_column_id /
   get_entity_capabilities / get_selectable_fields) resolve it, so every
   registry consumer — validator AND oql_lang's parse/render — agrees.

2. Quoted (exact-intent) search values no longer hard-error on entities with
   no `.search.exact` columns (= every non-works entity): the parser degrades
   them to the stemmed `.search` column, where the engine executes a quoted
   value as a real adjacency/phrase query. Render keeps the plain quoted form
   (byte-stable — on such entities quotes can only mean phrase), `stemmed "…"`
   folds into it, `within N (…)` proximity degrades the same way, and quoted
   WILDCARDS get a tailored hard error (nothing can execute them there).

    PYTHONPATH=. pytest tests/oql/test_entity_key_and_exact_fallback.py -q
"""
import pytest

from query_translation import oql_lang as L
from query_translation.validator import validate_oqo


# ---- fix 1: the `types` entity resolves registry fields --------------------

def test_types_resolves_name():
    oqo = L.parse("types where name has (article)")
    assert [(f.column_id, f.value) for f in oqo.filter_rows] == [
        ("display_name.search", "article")
    ]
    assert L.render(oqo) == "types where name has (article)"
    assert validate_oqo(oqo).valid


def test_types_resolves_nonsearch_fallback_fields():
    oqo = L.parse("types where works count > (1000)")
    assert [(f.column_id, f.value) for f in oqo.filter_rows] == [("works_count", 1000)]
    assert validate_oqo(oqo).valid


def test_resolve_entity_key():
    from core.properties import get_entity_properties, resolve_entity_key
    assert resolve_entity_key("types") == "work-types"
    assert resolve_entity_key("works") == "works"
    assert resolve_entity_key("nope") == "nope"
    assert get_entity_properties("types") is get_entity_properties("work-types")


# ---- fix 2: quoted values on exact-less entities ---------------------------

@pytest.mark.parametrize("entity,field", [
    ("authors", "name"), ("sources", "name"), ("types", "name"),
    ("authors", "text"),
])
def test_quoted_phrase_degrades_to_stemmed_column(entity, field):
    oqo = L.parse(f'{entity} where {field} has ("albert einstein")')
    (leaf,) = oqo.filter_rows
    assert leaf.column_id.endswith(".search")          # NOT .search.exact
    assert leaf.value == '"albert einstein"'           # quotes kept -> phrase
    assert validate_oqo(oqo).valid
    # byte-stable canonical: no `stemmed ` prefix on an exact-less entity
    assert L.render(oqo) == f'{entity} where {field} has ("albert einstein")'
    assert L.parse(L.render(oqo)).filter_rows == oqo.filter_rows


def test_stemmed_phrase_folds_to_plain_quotes_on_exactless_entity():
    oqo = L.parse('authors where name has (stemmed "albert einstein")')
    (leaf,) = oqo.filter_rows
    assert (leaf.column_id, leaf.value) == ("display_name.search", '"albert einstein"')
    assert L.render(oqo) == 'authors where name has ("albert einstein")'


def test_proximity_degrades_on_exactless_entity():
    oqo = L.parse('authors where name has (within 3 ("albert", "einstein"))')
    (leaf,) = oqo.filter_rows
    assert (leaf.column_id, leaf.value) == ("display_name.search", '"albert"~3~"einstein"')
    assert validate_oqo(oqo).valid
    assert L.parse(L.render(oqo)).filter_rows == oqo.filter_rows


def test_quoted_wildcard_rejected_on_exactless_entity():
    with pytest.raises(Exception) as exc:
        L.parse('authors where name has ("ein*")')
    assert "no exact search field" in str(exc.value)


def test_works_exact_path_unchanged():
    oqo = L.parse('works where title has ("machine learning")')
    (leaf,) = oqo.filter_rows
    assert (leaf.column_id, leaf.value) == ("display_name.search.exact", '"machine learning"')
    # works keeps the `stemmed "…"` render for stemmed phrases
    oqo2 = L.parse('works where title has (stemmed "machine learning")')
    assert L.render(oqo2) == 'works where title has (stemmed "machine learning")'
