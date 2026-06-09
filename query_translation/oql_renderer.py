"""
OQL Renderer — OQO -> canonical OQL string.

As of oxjob #376 this is a thin wrapper over the ONE OQL engine
(`query_translation.oql_lang`). The engine owns the canonical grammar + render
rules; this module's only job is to adapt prod's name-resolution surface (an
`entity_resolver(entity_id)` callable that hits Elasticsearch for native
entities, plus the built-in code->name tables for countries/languages/SDGs/…)
to the engine's `resolver(value, column_id)` contract.

See docs/oql-spec.md and query_translation/oql_lang.py.
"""

from typing import Optional, Dict, Any, Callable
import re

from query_translation.oqo import OQO
from query_translation import oql_lang


def _render_search_proximity(value: Any) -> Optional[str]:
    """Render a search proximity value back to its OQL surface (oxjob #355).

    `"phrase"~N` -> `"phrase" within N words`; binary `"A"~N~"B"` ->
    `"A" within N words of "B"`. Returns None for any non-proximity value.

    Retained for back-compat (the engine now renders proximity itself via
    `oql_lang._render_term`); kept because other modules import it.
    """
    if not isinstance(value, str):
        return None
    m = re.match(r'^"([^"]*)"~(\d+)~"([^"]*)"$', value)
    if m:
        return f'"{m.group(1)}" within {m.group(2)} words of "{m.group(3)}"'
    m = re.match(r'^"([^"]*)"~(\d+)$', value)
    if m:
        return f'"{m.group(1)}" within {m.group(2)} words'
    return None


# ---------------------------------------------------------------------------
# Resolver bridge: engine `resolver(value, column_id)` -> prod name resolution.
#
# The engine asks "what's the display name for this value on this column?" only
# for columns whose Field has resolves_name=True (entity-id columns + country
# codes). We map the column_id to its entity-type namespace, try the supplied
# `entity_resolver` (native ES lookup for institutions/authors/…), then fall
# back to the built-in code->name tables (countries/languages/continents/SDGs).
# ---------------------------------------------------------------------------

# column_id -> entity-type namespace, for the columns the engine resolves
# (oql_lang._FIELDS where resolves_name is True). `None` = not name-resolvable
# (e.g. a bare OpenAlex work id).
_RESOLVE_NAMESPACE: Dict[str, Optional[str]] = {
    "authorships.institutions.lineage": "institutions",
    "last_known_institutions.id": "institutions",
    "authorships.author.id": "authors",
    "primary_location.source.id": "sources",
    "primary_topic.id": "topics",
    "topics.id": "topics",
    "funders.id": "funders",
    "primary_location.source.publisher_lineage": "publishers",
    "primary_topic.field.id": "fields",
    "primary_topic.subfield.id": "subfields",
    "domain.id": "domains",
    "sustainable_development_goals.id": "sdgs",
    "authorships.countries": "countries",
    "country_code": "countries",
    "last_known_institutions.country_code": "countries",
    "language": "languages",
    # Citation-relationship filters reference a WORK; resolve its title (oxjob #363
    # case 7). cited_by = the work's references; cites = works citing it.
    "cited_by": "works",
    "cites": "works",
    # oxjob #402 — the other two work-relationship id filters resolve the same way.
    "referenced_works": "works",
    "related_to": "works",
    "ids.openalex": None,
    # oxjob #402 friendly-name audit — corresponding-author/-institution ids
    # resolve via the same namespaces as `author` / `institution`.
    "corresponding_author_ids": "authors",
    "corresponding_institution_ids": "institutions",
    # oxjob #402 batch 6 — best_oa_location / locations source-id mirrors resolve via the
    # sources namespace, like primary_location.source.id ("source").
    "best_oa_location.source.id": "sources",
    "locations.source.id": "sources",
    # oxjob #402 batch 7 — grant/award entity ids resolve via the awards namespace.
    "awards.id": "awards",
    # continent ids (continents/Q15) resolve to a name via the continents namespace.
    "authorships.institutions.continent": "continents",
    # keyword entity ids resolve to a name via the keywords namespace (#402, GUI parity).
    "keywords.id": "keywords",
}

# Built-in code/id -> display-name tables for the non-native entity types that
# ES doesn't resolve by `get_display_name` (the `entity_resolver` returns None):
#   - fields / subfields / domains: numeric path-style IDs (`fields/27`) that
#     `normalize_openalex_id` can't route (it only matches single-letter-prefixed
#     IDs), so they NEVER resolved via ES — the cause of `field is 27` rendering
#     with no `[Medicine]` annotation (oxjob #363 case 5).
#   - languages / countries / continents / sdgs / types / oa-statuses: closed
#     code vocabularies ES doesn't index for name lookup.
# All of these have a complete `values` list in the repo `config/*.yaml`, so we
# read the display names straight from there — full coverage, no ES, no network.
import os
try:
    import yaml as _yaml
except Exception:  # pragma: no cover - yaml is a prod dep, but stay defensive
    _yaml = None

_CONFIG_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config"
)
# resolver namespace -> config/<file>.yaml
_CONFIG_YAML_BY_NS: Dict[str, str] = {
    "fields": "fields.yaml",
    "subfields": "subfields.yaml",
    "domains": "domains.yaml",
    "languages": "languages.yaml",
    "countries": "countries.yaml",
    "continents": "continents.yaml",
    "sdgs": "sdgs.yaml",
    "types": "work-types.yaml",
    "oa-statuses": "oa-statuses.yaml",
}
# namespace -> {short_id.lower(): display_name}, loaded lazily + cached.
_CONFIG_TABLES: Dict[str, Dict[str, str]] = {}


def _config_table(entity_type: Optional[str]) -> Optional[Dict[str, str]]:
    """Load (once) the `config/<entity_type>.yaml` `values` list into a
    {short_id.lower(): display_name} table. Returns None for namespaces with no
    config file (native ES entities, or `works`). Defensive: any load failure
    yields an empty table rather than raising into a render."""
    if entity_type not in _CONFIG_YAML_BY_NS:
        return None
    if entity_type not in _CONFIG_TABLES:
        table: Dict[str, str] = {}
        path = os.path.join(_CONFIG_DIR, _CONFIG_YAML_BY_NS[entity_type])
        try:
            if _yaml is not None:
                with open(path) as fh:
                    for row in (_yaml.safe_load(fh) or {}).get("values", []):
                        rid = str(row.get("id", ""))
                        short = rid.split("/", 1)[1] if "/" in rid else rid
                        name = row.get("display_name")
                        if short and name:
                            table[short.lower()] = name
        except Exception:  # pragma: no cover - missing/corrupt config
            table = {}
        _CONFIG_TABLES[entity_type] = table
    return _CONFIG_TABLES[entity_type]


def _builtin_name(entity_type: Optional[str], short_id: str) -> Optional[str]:
    """Resolve a non-native entity code/id to its display name from config yaml."""
    table = _config_table(entity_type)
    if table is not None:
        return table.get(short_id.lower())
    return None


def _normalize_code(value: Any) -> Optional[str]:
    """Reduce an OQO value to the casefolded short code the config tables key on
    (strip any `…/` URL/path prefix, lowercase). None for non-strings."""
    if not isinstance(value, str):
        return None
    short = value.split("/", 1)[1] if "/" in value else value
    return short.lower()


def is_closed_config_vocab(namespace: Optional[str]) -> bool:
    """True if `namespace` is a closed code-vocabulary backed by a `config/*.yaml`
    `values` list (countries, languages, sdgs, types, oa-statuses, …). The
    single source of truth for closed-vocab membership — the validator's
    value-domain check keys off the SAME tables this renderer resolves names
    from, so a value validates iff it can also be rendered with a name."""
    return namespace in _CONFIG_YAML_BY_NS


def is_vocab_member(namespace: Optional[str], value: Any) -> bool:
    """True if `value` is a member of the closed config vocab `namespace`.
    Normalizes exactly like `_builtin_name` (URL-prefix strip + casefold), so
    membership and name-resolution can never disagree. Callers should gate on
    `is_closed_config_vocab(namespace)` first — a non-vocab namespace returns
    False here (its table is None), which is not the same as "not a member"."""
    table = _config_table(namespace)
    if table is None:
        return False
    code = _normalize_code(value)
    return code is not None and code in table


def vocab_name_to_code(namespace: Optional[str], name: str) -> Optional[str]:
    """Reverse lookup: a display name -> its code (for "did you mean" fix-its,
    e.g. `country is Canada` -> suggest `ca`). Case-insensitive; None if no
    name matches. Built lazily from the same config table."""
    table = _config_table(namespace)
    if table is None or not isinstance(name, str):
        return None
    want = name.strip().lower()
    for code, display in table.items():
        if display.lower() == want:
            return code
    return None


def make_engine_resolver(
    entity_resolver: Optional[Callable[[str], Optional[str]]] = None
) -> Callable[[str, str], Optional[str]]:
    """Adapt prod's `entity_resolver(entity_id)` + built-in tables to the
    engine's `resolver(value, column_id)` contract. Caches per (type, id)."""
    cache: Dict[str, Optional[str]] = {}

    def resolve(value: Any, column_id: str) -> Optional[str]:
        if not isinstance(value, str):
            return None
        ns = _RESOLVE_NAMESPACE.get(column_id)
        if ns is None:
            return None
        short_id = value.split("/", 1)[1] if "/" in value else value
        key = f"{ns}/{short_id}"
        if key in cache:
            return cache[key]
        name = None
        if entity_resolver:
            try:
                name = entity_resolver(key)
            except Exception:
                name = None
        if not name:
            name = _builtin_name(ns, short_id)
        cache[key] = name
        return name

    return resolve


def render_oqo_to_oql(
    oqo: OQO,
    entity_resolver: Optional[Callable[[str], Optional[str]]] = None,
) -> str:
    """Render an OQO to canonical OQL (delegates to the engine).

    Args:
        oqo: the OQO to render
        entity_resolver: optional `entity_id -> display name` callable (native
            ES lookup). Built-in code->name tables cover the rest.
    """
    return oql_lang.render(oqo, resolver=make_engine_resolver(entity_resolver))
