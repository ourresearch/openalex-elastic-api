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
    "primary_topic.field.id": "fields",
    "domain.id": "domains",
    "sustainable_development_goals.id": "sdgs",
    "authorships.countries": "countries",
    "country_code": "countries",
    "last_known_institutions.country_code": "countries",
    "ids.openalex": None,
}

# Built-in code -> display-name tables for non-native entity types (the
# `entity_resolver` returns None for these; ES doesn't index them).
LANGUAGES = {
    "en": "English", "zh": "Chinese", "es": "Spanish", "fr": "French",
    "de": "German", "ja": "Japanese", "pt": "Portuguese", "ru": "Russian",
    "ko": "Korean", "it": "Italian", "ar": "Arabic", "nl": "Dutch",
    "pl": "Polish", "tr": "Turkish", "id": "Indonesian", "cs": "Czech",
    "sv": "Swedish", "fa": "Persian", "uk": "Ukrainian", "vi": "Vietnamese",
}

COUNTRIES = {
    "us": "United States", "gb": "United Kingdom", "cn": "China",
    "de": "Germany", "fr": "France", "jp": "Japan", "ca": "Canada",
    "au": "Australia", "in": "India", "br": "Brazil", "it": "Italy",
    "es": "Spain", "kr": "South Korea", "nl": "Netherlands", "ru": "Russia",
    "ch": "Switzerland", "se": "Sweden", "pl": "Poland", "be": "Belgium",
    "at": "Austria", "dk": "Denmark", "no": "Norway", "fi": "Finland",
    "mx": "Mexico", "sg": "Singapore", "ie": "Ireland", "nz": "New Zealand",
    "pt": "Portugal", "za": "South Africa", "il": "Israel",
}

CONTINENTS = {
    "q15": "Africa", "q18": "South America", "q46": "Europe",
    "q48": "Asia", "q49": "North America", "q55643": "Oceania",
    "q51": "Antarctica", "africa": "Africa", "south america": "South America",
    "europe": "Europe", "asia": "Asia", "north america": "North America",
    "oceania": "Oceania", "antarctica": "Antarctica",
}

SDGS = {
    "1": "No Poverty", "2": "Zero Hunger", "3": "Good Health and Well-being",
    "4": "Quality Education", "5": "Gender Equality",
    "6": "Clean Water and Sanitation", "7": "Affordable and Clean Energy",
    "8": "Decent Work and Economic Growth", "9": "Industry, Innovation and Infrastructure",
    "10": "Reduced Inequalities", "11": "Sustainable Cities and Communities",
    "12": "Responsible Consumption and Production", "13": "Climate Action",
    "14": "Life Below Water", "15": "Life on Land",
    "16": "Peace, Justice, and Strong Institutions", "17": "Partnerships for the Goals",
}


def _builtin_name(entity_type: Optional[str], short_id: str) -> Optional[str]:
    """Resolve well-known non-native entity codes to display names."""
    if entity_type == "types":
        return short_id.replace("-", " ").title()
    if entity_type == "oa-statuses":
        return short_id.title()
    if entity_type == "languages":
        return LANGUAGES.get(short_id.lower())
    if entity_type == "countries":
        return COUNTRIES.get(short_id.lower())
    if entity_type == "continents":
        return CONTINENTS.get(short_id.lower())
    if entity_type == "sdgs":
        return SDGS.get(short_id)
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
