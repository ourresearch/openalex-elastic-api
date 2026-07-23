"""#455 — alias column_id spellings canonicalize to one identity at every OQO
construction boundary (OQL parse, URL parse, from_dict) and in the canonicalizer.

A property has ONE identity but many filter-namespace spellings (`is_oa` ==
`open_access.is_oa`; `institution.id` == `authorships.institutions.id`; `cites` ==
`referenced_works`; `journal` == `primary_location.source.id`). After #455 an alias
input and its canonical input produce the SAME internal OQO column_id and the SAME
canonicalizer cache key — so an identity renders, caches, and round-trips one way
regardless of which spelling the user typed (ACC Test 1).

These run under the offline `tests/oql` gate (no DB/ES); the canonicalization map
is read from the already-built `core.properties.ENTITY_PROPERTIES`.
"""

import pytest

from query_translation.oql_lang import parse
from query_translation.oqo import OQO, LeafFilter, GroupBy, SortBy, canonicalize_oqo_column_ids
from query_translation.oqo_canonicalizer import canonicalize_oqo
from query_translation.url_parser import parse_url_to_oqo
from core.properties import canonicalize_column_id


# (entity, alias, canonical) — representative filter-namespace pairs from #446.
PAIRS = [
    ("works", "is_oa", "open_access.is_oa"),
    ("works", "institution.id", "authorships.institutions.id"),
    ("works", "cites", "referenced_works"),
    ("works", "journal", "primary_location.source.id"),
]


@pytest.mark.parametrize("entity,alias,canon", PAIRS)
def test_helper_maps_alias_to_canonical(entity, alias, canon):
    assert canonicalize_column_id(alias, entity) == canon
    # canonical and unknown columns pass through unchanged (idempotent / safe)
    assert canonicalize_column_id(canon, entity) == canon
    assert canonicalize_column_id("not_a_real_col", entity) == "not_a_real_col"
    assert canonicalize_column_id(alias, "no_such_entity") == alias


def test_oqo_walker_is_idempotent_and_pure():
    oqo = OQO(
        get_rows="works",
        filter_rows=[LeafFilter(column_id="is_oa", value=True)],
        sort_by=[SortBy(column_id="cites", direction="desc")],
        group_by=[GroupBy(column_id="journal")],
    )
    once = canonicalize_oqo_column_ids(oqo)
    twice = canonicalize_oqo_column_ids(once)
    assert once.to_dict() == twice.to_dict()              # idempotent
    assert oqo.filter_rows[0].column_id == "is_oa"        # input not mutated
    assert once.filter_rows[0].column_id == "open_access.is_oa"
    assert once.sort_by[0].column_id == "referenced_works"
    assert once.sort_by[0].direction == "desc"            # other attrs preserved
    assert once.group_by[0].column_id == "primary_location.source.id"


# Every alias spelling of a supported identity is an OQL `where` word: curated
# words parse via `_FIELDS`, technical alias columns (`institution.id`, `journal`)
# via the raw-column_id door, which resolves them to the canonical (#455 Phase C).
OQL_PARSEABLE_PAIRS = [
    ("works", "is_oa", "open_access.is_oa", "true"),
    ("works", "cites", "referenced_works", "w1984893742"),
    ("works", "institution.id", "authorships.institutions.id", "i33213144"),
    ("works", "journal", "primary_location.source.id", "s137773608"),
]


@pytest.mark.parametrize("entity,alias,canon,val", OQL_PARSEABLE_PAIRS)
def test_oql_parse_alias_equals_canonical(entity, alias, canon, val):
    a = parse(f"{entity} where {alias} is {val}")
    b = parse(f"{entity} where {canon} is {val}")
    assert a.filter_rows[0].column_id == canon
    assert a.to_dict() == b.to_dict()
    # same canonicalizer cache key regardless of input spelling
    assert canonicalize_oqo(a).to_dict() == canonicalize_oqo(b).to_dict()


def test_url_parse_canonicalizes_filter_sort_group():
    u = parse_url_to_oqo(
        entity_type="works",
        filter_string="is_oa:true",
        group_by_string="institution.id",
        sort_string="cites:desc",
    )
    assert u.filter_rows[0].column_id == "open_access.is_oa"
    assert u.group_by[0].column_id == "authorships.institutions.id"
    assert u.sort_by[0].column_id == "referenced_works"
    assert u.sort_by[0].direction == "desc"


def test_from_dict_canonicalizes_at_json_boundary():
    d = {
        "get_rows": "works",
        "filter_rows": [{"column_id": "is_oa", "value": True}],
        "sort_by": [{"column_id": "cites", "direction": "desc"}],
        "group_by": [{"column_id": "journal"}],
    }
    oqo = OQO.from_dict(d)
    assert oqo.filter_rows[0].column_id == "open_access.is_oa"
    assert oqo.sort_by[0].column_id == "referenced_works"
    assert oqo.group_by[0].column_id == "primary_location.source.id"


def test_select_is_NOT_canonicalized_via_filter_aliases():
    # The column/select namespace is separate from the filter namespace (#450):
    # on authors `id`'s filter-alias canonical is `ids.openalex`, which is NOT a
    # valid `?select=` column. The walker must leave `select` untouched so result
    # projection is not corrupted (column-namespace canon is deferred to Phase B/C).
    oqo = OQO(get_rows="authors", select=["id", "display_name"])
    out = canonicalize_oqo_column_ids(oqo)
    assert out.select == ["id", "display_name"]


def test_synthetic_sort_keys_pass_through():
    oqo = OQO(get_rows="works", sort_by=[SortBy(column_id="relevance_score", direction="desc")])
    out = canonicalize_oqo_column_ids(oqo)
    assert out.sort_by[0].column_id == "relevance_score"


def test_unlisted_alias_canonicalizes_but_is_not_advertised():
    # #593: `last_known_authorships.institutions.lineage` is a never-valid authors
    # key manufactured by a GUI URL-rewrite bug (2026-01 → 2026-07) that lives on
    # in users' bookmarks. It's an `unlisted` alias: it must resolve + canonicalize
    # like any alias, but must NOT be advertised in the canonical property's public
    # `alternate_keys` (unlisted = "accept, never advertise").
    from core.properties import ENTITY_PROPERTIES

    mangled = "last_known_authorships.institutions.lineage"
    canon = "last_known_institutions.id"
    assert canonicalize_column_id(mangled, "authors") == canon
    props = ENTITY_PROPERTIES["authors"]
    assert mangled in props  # still a live, resolvable column
    assert mangled not in props[canon].alternate_keys  # never advertised
    u = parse_url_to_oqo(entity_type="authors", filter_string=f"{mangled}:i90183372")
    assert u.filter_rows[0].column_id == canon


# --- #455 Phase C/D: works friendly renders from registry display_names -------
# Works joined the tier-3 entity-fallback render (Jason 2026-07-23, option D): a
# supported works identity with no curated `_FIELDS` word renders its registry
# display_name — which therefore also parses (round-trip by construction).
# Collision words and uncurated booleans keep the raw-id render, which always
# round-trips via the raw-column_id door.

from query_translation.oql_renderer import render_oqo_to_oql  # noqa: E402


WORKS_DN_RENDER = [
    ("authorships.institutions.id", "exact institution", "I33213144"),
    ("apc_list.value_usd", "APC list price USD", "2000"),
    ("locations.source.host_organization_lineage", "any location publisher",
     "P4310320990"),
]


@pytest.mark.parametrize("canon,word,val", WORKS_DN_RENDER)
def test_works_registry_display_name_renders_and_round_trips(canon, word, val):
    a = parse(f"works where {canon} is {val}")
    b = parse(f"works where {word} is {val}")
    assert a.to_dict() == b.to_dict()          # word and raw id are the same query
    r = render_oqo_to_oql(a)
    assert word in r
    r2 = render_oqo_to_oql(parse(r.replace(" [no entity found]", "")))
    assert r2 == r                             # render is a fixpoint


def test_works_collision_and_uncurated_bool_render_raw():
    # "domain" is owned by primary_topic.domain.id -> topics.domain.id stays raw.
    r = render_oqo_to_oql(parse("works where topics.domain.id is D1"))
    assert "topics.domain.id" in r
    # Uncurated bool: no sentence phrasing -> raw-id render, still parseable.
    r = render_oqo_to_oql(parse("works where has_content.grobid_xml is true"))
    assert "has_content.grobid_xml" in r
