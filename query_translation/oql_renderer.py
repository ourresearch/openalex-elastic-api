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

from query_translation.oqo import OQO
from query_translation import oql_lang


# ---------------------------------------------------------------------------
# Resolver bridge: engine `resolver(value, column_id)` -> prod name resolution.
#
# The engine asks "what's the display name for this value on this column?" only
# for columns that derive an annotation namespace from the registry
# (`oql_lang.namespace_for_column`, oxjob #565 — formerly the hand-maintained
# `_RESOLVE_NAMESPACE` map here, the #418/#455 drift class). We map the
# column_id to its entity-type namespace, try the supplied `entity_resolver`
# (native ES lookup for institutions/authors/…), then fall back to the
# built-in code->name tables (countries/languages/continents/SDGs).
# ---------------------------------------------------------------------------

# Built-in code/id -> display-name tables for the non-native entity types that
# ES doesn't resolve by `get_display_name` (the `entity_resolver` returns None):
#   - fields / subfields / domains: numeric path-style IDs (`fields/27`) that
#     `normalize_openalex_id` can't route (it only matches single-letter-prefixed
#     IDs), so they NEVER resolved via ES — the cause of `field is 27` rendering
#     with no `[Medicine]` annotation (oxjob #363 case 5).
#   - languages / countries / continents / sdgs / types / oa-statuses: closed
#     code vocabularies ES doesn't index for name lookup.
# All of these have a complete `values` list in `config/*.yaml`, already loaded
# by THE entity registry (`core.entities`, oxjob #405) — read the display names
# from there rather than keeping a second yaml loader in sync.

# renderer namespace -> registry entity name, where they differ.
_REGISTRY_NS_ALIAS: Dict[str, str] = {"types": "work-types"}
# namespace -> {short_id.lower(): display_name}, built lazily + cached.
_CONFIG_TABLES: Dict[str, Optional[Dict[str, str]]] = {}


def _config_table(entity_type: Optional[str]) -> Optional[Dict[str, str]]:
    """The closed-vocab `values` of `entity_type` as a {short_id.lower():
    display_name} table, from the core entity registry. Returns None for
    open/native namespaces (no `values` list). Defensive: any registry failure
    yields None rather than raising into a render."""
    if entity_type not in _CONFIG_TABLES:
        table: Optional[Dict[str, str]] = None
        try:
            from core.entities import get_entity_type
            ent = get_entity_type(_REGISTRY_NS_ALIAS.get(entity_type, entity_type))
            if ent is not None and ent.values:
                table = {}
                for row in ent.values:
                    rid = str(row.get("id", ""))
                    short = rid.split("/", 1)[1] if "/" in rid else rid
                    name = row.get("display_name")
                    if short and name:
                        table[short.lower()] = name
        except Exception:  # pragma: no cover - registry unavailable/corrupt
            table = None
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


def is_vocab_member(namespace: Optional[str], value: Any) -> bool:
    """True if `value` is a member of the closed config vocab `namespace`.
    Normalizes exactly like `_builtin_name` (URL-prefix strip + casefold), so
    membership and name-resolution can never disagree. A non-vocab namespace
    returns False here (its table is None), which is not the same as "not a
    member" — callers deciding *whether* to domain-check should key off their
    own namespace map (see validator.CLOSED_VOCAB_NAMESPACE)."""
    table = _config_table(namespace)
    if table is None:
        return False
    code = _normalize_code(value)
    return code is not None and code in table


def config_vocab_items(namespace: Optional[str]):
    """Public: the full closed-vocab membership of `namespace` as a sorted list of
    ``(short_id, display_name)`` tuples — the editor's enum-value autocomplete source
    (#357). Empty list for a non-vocab namespace. Sorted by display name for a stable,
    human-friendly dropdown order."""
    table = _config_table(namespace)
    if not table:
        return []
    return sorted(table.items(), key=lambda kv: kv[1].lower())


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
    entity_resolver: Optional[Callable[[str], Optional[str]]] = None,
    entity: Optional[str] = None,
) -> Callable[[str, str], Optional[str]]:
    """Adapt prod's `entity_resolver(entity_id)` + built-in tables to the
    engine's `resolver(value, column_id)` contract. Caches per (type, id).

    `entity` (the OQO's `get_rows`, when the caller has one) is the namespace-
    derivation preference for homonym columns; omitted, derivation is
    entity-blind (works-first). The returned callable exposes `.covers` so the
    engine's annotate/[no entity found] gate uses the SAME derivation as the
    lookup (oxjob #565)."""
    cache: Dict[str, Optional[str]] = {}

    def resolve(value: Any, column_id: str) -> Optional[str]:
        if not isinstance(value, str):
            return None
        ns = oql_lang.namespace_for_column(column_id, entity)
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

    resolve.covers = (
        lambda column_id: oql_lang.namespace_for_column(column_id, entity) is not None
    )
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
    resolver = make_engine_resolver(entity_resolver, entity=oqo.get_rows)
    return oql_lang.render(oqo, resolver=resolver)
