"""
Shared builder for the private `meta.x_query` triple {oql, oqo, url} (oxjob #373/#378).

`x_query` is the canonical multi-form representation of an executed query that the
GUI rehydrates from (oxjob #378: the server's query object is the source of truth,
not the raw URL). Originally introduced on the OQL/OQO execute path (#373); #378
emits it on *every* entity response (`core/shared_view.py`) so the chips view can
source itself from `x_query.url` rather than re-parsing the route.

This module is intentionally dependency-light — it imports only the translation
layer (`oqo_canonicalizer`, `url_renderer`, `oql_renderer`) plus `core.utils` for
display-name resolution. It must NOT import `core.shared_view`, `query_translation.views`,
or `query_translation.execution`, all of which depend on it (or on `shared_view`),
to keep the import graph acyclic.
"""

import urllib.parse
from typing import Callable, Optional

from core.utils import get_display_name as _get_display_name
from query_translation import oql_lang
from query_translation.oqo import OQO
from query_translation.oqo_canonicalizer import canonicalize_oqo
from query_translation.oql_renderer import render_oqo_to_oql
from query_translation.url_renderer import URLRenderError, render_oqo_to_url


# Entity types that exist in Elasticsearch and can be looked up for display names.
# Entity types `get_display_name` can resolve via ES by OpenAlex ID. These all
# have single-letter-prefixed IDs (I…, A…, S…, W…) that `normalize_openalex_id`
# routes to an index. `works` is here so the cited_by/cites filters resolve a
# work's title (oxjob #363 case 7). fields/subfields/domains are intentionally
# NOT here: their IDs are numeric path-style (`fields/27`) which `get_display_name`
# can't route — they resolve from config/*.yaml in the renderer's _builtin_name.
NATIVE_ENTITY_TYPES = {
    "institutions", "authors", "sources", "publishers", "funders", "topics",
    "keywords", "concepts", "works",
}

# The order components appear in a rendered oxurl (mirrors the API's param order).
_OXURL_COMPONENT_ORDER = (
    "search.semantic", "filter", "sort", "group_by", "select", "sample", "seed",
    "per_page", "page", "cursor",
)


def safe_get_display_name(entity_id: str):
    """
    Resolve entity display name from Elasticsearch for native entity types.

    Only queries Elasticsearch for entities that actually exist there.
    Non-native types (types, languages, countries, etc.) return None
    and are handled by the renderer's built-in lookup tables.

    The entity_id comes in as "institutions/i33213144" but get_display_name
    expects just the short ID "i33213144" (it prepends https://openalex.org/).
    """
    if not entity_id or "/" not in entity_id:
        return None

    entity_type, short_id = entity_id.split("/", 1)
    if entity_type not in NATIVE_ENTITY_TYPES:
        return None  # Let default resolver handle it

    try:
        # Pass just the short ID - get_display_name prepends the URL
        return _get_display_name(short_id)
    except Exception:
        return None


def _components_to_oxurl(entity_type: str, components: dict) -> str:
    """Build a readable OpenAlex URL string (e.g. `/works?filter=type:article`)
    from the entity type + the component dict returned by render_oqo_to_url.

    `:` `, ` `|` are left un-encoded (readable filter syntax); spaces and other
    reserved chars are percent-encoded so the URL is still valid.
    """
    pairs = []
    for key in _OXURL_COMPONENT_ORDER:
        value = components.get(key)
        if value is None or value == "":
            continue
        pairs.append(f"{key}={urllib.parse.quote(str(value), safe=':, |')}")
    base = f"/{entity_type}"
    return base + ("?" + "&".join(pairs) if pairs else "")


def build_x_query(
    oqo: OQO,
    entity_resolver: Optional[Callable[[str], Optional[str]]] = None,
) -> dict:
    """Build the private `meta.x_query` triple {oql, oqo, url} (oxjob #373).

    The canonical multi-form representation of the executed query:
      - oql: re-rendered canonical OQL (round-trips: re-parsing it yields `oqo`)
      - oqo: the canonical structured query object the client hydrates from
      - url: the OXURL (`/works?filter=…`) form, or None when the OQO isn't
             URL-expressible (nested boolean trees, multi-dim group_by) — the URL
             syntax is a lossy subset of OQO, so this is null, never a 500.

    `x_query` is deliberately **private/unstable**: `x_` prefix, undocumented,
    injected onto the serialized `meta` and kept out of `/properties` + the docs.

    `entity_resolver` resolves entity IDs to display names so `x_query.oql` reads
    `institution is I136199984 [Harvard]` instead of a bare ID. Both executed-query
    callers — the `/?oql=` execute path (`query_translation/execution.py`) and the
    per-entity SERP path (`core/shared_view.py`) — pass None (OQLO charter
    decision 14, #378 S3): canonical OQL = bare IDs, pure string work, no lookups.
    That's fine because nothing consumes the executed-path `oql` for display
    (chips come from `url`; the "too complex" OQL card only appears when
    `url is None`, which never happens for a query that arrived as a URL).

    With no entity_resolver the engine renderer must get `resolver=None` — fully
    bare, not even the local `config/*.yaml` builtin names. Wrapping a None
    entity_resolver in `make_engine_resolver` (the pre-fix behavior) hands the
    engine a truthy-but-empty resolver, and the engine can't tell "nothing was
    looked up" from "looked up and missed" — so every resolvable entity ID a user
    executed got a false `[no entity found]` annotation (oxjob #363 / #418).
    """
    canonical = canonicalize_oqo(oqo)

    url_form = None
    try:
        components = render_oqo_to_url(canonical)
        url_form = _components_to_oxurl(canonical.get_rows, components)
    except URLRenderError:
        # Not URL-expressible (e.g. nested boolean tree). url stays None; the
        # client treats null as an "advanced query" it can't render as chips.
        pass

    if entity_resolver is not None:
        oql_form = render_oqo_to_oql(canonical, entity_resolver=entity_resolver)
    else:
        # Executed-query path (decision 14): bare-ID canonical OQL, no resolver
        # object at all — see the docstring for why wrapping None is a bug.
        oql_form = oql_lang.render(canonical, resolver=None)

    return {
        "oql": oql_form,
        "oqo": canonical.to_dict(),
        "url": url_form,
    }
