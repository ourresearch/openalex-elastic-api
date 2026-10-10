"""Walks and sets in the pipeline language (oxjob #1535, Rung 2 of #1512).

A walk moves a query from works to the things they relate to and back:

    get works where institution is (I146416000); then get each author of those works;
    then get all that author's works; then, summarize using mean FWCI

`get each <noun> of those works` walks out (one result per thing), `get <nouns> of
those works` walks out to one combined set, and `get all that <noun>'s works` /
`get all those <nouns>' works` walks back to everything those things did. The OQO
carries them as `walks` (oqo.Walk); this module holds the vocabulary and the type
rules the parser, renderer, validator and executor share.
"""
from typing import Dict, Optional, Tuple

# Each walkable thing and the works column that links works to it: the column its
# noun means in a filter (`source is (...)` is the journal of record), so a walk
# lands on exactly the things `group those works by <noun>` lists. The other
# links (`any location source`, `topics`) stay filter words with no walk form.
WALK_LINKS: Dict[str, str] = {
    "authors": "authorships.author.id",
    "institutions": "authorships.institutions.lineage",
    "sources": "primary_location.source.id",
    "publishers": "primary_location.source.host_organization_lineage",
    "funders": "funders.id",
    "topics": "primary_topic.id",
    "subfields": "primary_topic.subfield.id",
    "fields": "primary_topic.field.id",
    "domains": "primary_topic.domain.id",
    "keywords": "keywords.id",
    "sdgs": "sustainable_development_goals.id",
    "countries": "authorships.countries",
}
LINK_ENTITY: Dict[str, str] = {col: ent for ent, col in WALK_LINKS.items()}
# column aliases that mean the same link (the registry's canonical spellings)
LINK_ENTITY.update({"domain.id": "domains"})
# a role on the works (oxjob #1555): `get each corresponding author of those works`
ROLE_LINKS: Dict[str, Tuple[str, str]] = {
    "corresponding_author_ids": ("authors", "corresponding author"),
    "corresponding_institution_ids": ("institutions", "corresponding institution"),
}
LINK_ENTITY.update({col: ent for col, (ent, _w) in ROLE_LINKS.items()})

# (singular, plural) as written after `get each` / `get`; matched case-insensitively
NOUNS: Dict[str, Tuple[str, str]] = {
    "authors": ("author", "authors"),
    "institutions": ("institution", "institutions"),
    "sources": ("source", "sources"),
    "publishers": ("publisher", "publishers"),
    "funders": ("funder", "funders"),
    "topics": ("topic", "topics"),
    "subfields": ("subfield", "subfields"),
    "fields": ("field", "fields"),
    "domains": ("domain", "domains"),
    "keywords": ("keyword", "keywords"),
    "sdgs": ("SDG", "SDGs"),
    "countries": ("country", "countries"),
}
_BY_WORD: Dict[str, Tuple[str, bool]] = {}
for _ent, (_one, _many) in NOUNS.items():
    _BY_WORD[_one.lower()] = (_ent, False)
    _BY_WORD[_many.lower()] = (_ent, True)
# a few spellings people write
_BY_WORD.update({"journal": ("sources", False), "journals": ("sources", True),
                 "sustainable development goal": ("sdgs", False)})

# Things whose own fields a walk's `where` can filter (their index is in
# core/join_resolver.py); countries have no index to look them up in.
WHERE_ENTITIES = {"authors", "institutions", "sources", "publishers", "funders", "topics",
                  "subfields", "fields", "domains", "keywords", "sdgs"}


def noun_entity(word: str) -> Optional[Tuple[str, bool]]:
    """(entity, is_plural) for a walk noun, or None."""
    return _BY_WORD.get((word or "").lower())


def singular(entity: str) -> str:
    return NOUNS[entity][0] if entity in NOUNS else entity.rstrip("s")


def plural(entity: str) -> str:
    return NOUNS[entity][1] if entity in NOUNS else entity


def possessive(entity: str, each: bool) -> str:
    """`that author's` (one at a time) or `those authors'` (the combined set)."""
    if each:
        return f"that {singular(entity)}'s"
    p = plural(entity)
    return f"those {p}'" if p.endswith("s") else f"those {p}'s"


def link_for(entity: str) -> Optional[str]:
    """The works column a thing's works hang on (`all that author's works`)."""
    return WALK_LINKS.get(entity)


def entity_for_link(column_id: Optional[str]) -> Optional[str]:
    return LINK_ENTITY.get(column_id) if column_id else None


def walk_state(oqo) -> Tuple[str, bool, Optional[str]]:
    """(what the query holds now, one result per thing?, the link column) after the
    OQO's walks: `("works", True, "authorships.author.id")` after `get each author
    of those works; then get all that author's works`."""
    entity = oqo.get_rows
    each = bool(oqo.each)
    link = link_for(entity) if entity != "works" else None
    for w in oqo.walks:
        if w.to is not None:
            entity = w.to
        else:
            link = w.column_id
            entity = entity_for_link(w.column_id) or entity
            each = bool(w.each)
    return entity, each, link
