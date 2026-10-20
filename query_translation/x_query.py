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
from collections import OrderedDict
from typing import Callable, Dict, List, Optional

from core.utils import get_display_name as _get_display_name
from query_translation import oql_lang
from query_translation.oqo import OQO
from query_translation.oqo_canonicalizer import canonicalize_oqo
from query_translation.oql_renderer import render_oqo_to_oql
from query_translation.diagnostics import OQLError
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
    "search.semantic", "filter", "corpus", "sort", "group_by", "select",
    "sample", "seed", "per_page", "page", "cursor",
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
    if entity_type == "collections":
        from core.collection_resolver import collection_display_name
        return collection_display_name(short_id)
    if entity_type not in NATIVE_ENTITY_TYPES:
        return None  # Let default resolver handle it

    try:
        if entity_type == "keywords":
            # Keywords have a slug-based, path-namespaced canonical id
            # (https://openalex.org/keywords/<slug>) that get_display_name can't
            # resolve: get_index_name_by_id / normalize_openalex_id only handle
            # letter+digit ids (I/A/S/T/C…), so a keyword raised + returned None,
            # rendering valid keyword filters as "[no entity found]" in the OQL
            # string AND the builder (oxjob #428). Resolve them against the
            # keywords index instead, keyed by the full URL it stores.
            from core.group_by.display_names import (
                get_display_names_keywords_licenses_topics,
            )
            full_id = f"https://openalex.org/{entity_id}"
            names = get_display_names_keywords_licenses_topics([full_id]) or {}
            return names.get(full_id)
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


def _request_arg(name: str, allowed) -> Optional[str]:
    """`?name=` when it's one of `allowed`, else None (also outside a request)."""
    try:
        from flask import has_request_context, request
        if has_request_context() and request.args.get(name) in allowed:
            return request.args.get(name)
    except Exception:
        pass
    return None


def requested_style() -> Optional[str]:
    """`?oql_style=pipeline` previews the launch's echo on one request, so the website
    and the MCP server can test against it before the flip (oxjob #1530);
    `?oql_style=core` previews OQL core v3 (oxjob #1555, 2026-10-11) the same way. None
    otherwise (the configured CANONICAL_STYLE applies)."""
    return _request_arg("oql_style", ("pipeline", "classic", "core"))


def effective_style() -> str:
    """The echo style for this request: `?oql_style=` when given, else the configured
    CANONICAL_STYLE (so the core flip is one config change, oxjob #1555)."""
    from query_translation import oql_lang
    return requested_style() or oql_lang.CANONICAL_STYLE


def baseline_wanted() -> bool:
    """Only `?baseline=true` adds the all-works baseline. Held, off for users (Jason
    2026-10-12: "users shouldn't get a magic extra summary row with their query. They
    should just get the thing they asked for"); an option to decide later (charter OQLO)."""
    return _request_arg("baseline", ("true",)) == "true"


def new_oql(oqo: OQO, resolver=None) -> Optional[str]:
    """The new canonical form, `x_new_oql`, beside every `oql` until the flip (Jason
    2026-10-13: both forms everywhere, so we and others can try the new one): OQL core
    v3 (oxjob #1555) where it can say the query, else today's pipeline text, which is
    what the flip shows. None when no honest OQL exists (as for `oql`)."""
    from query_translation.oql_core import render_core
    try:
        return render_core(oqo, resolver) or oql_lang.render(oqo, resolver=resolver, style="pipeline")
    except OQLError:
        return None


# Names for the new form on the OQL execute path (oxjob #1555, found by #1744): the IDs are
# found with a render that does no I/O, then named in one `terms` query per index
# (`analytics._id_names`), with a process cache. Collections and keywords are looked up one by
# one (a few at most) and collections aren't cached (their names are per viewer). A miss is
# a bare link `(I123)`, still exact OQL.
_ECHO_NAMES: "OrderedDict[str, str]" = OrderedDict()
_ECHO_NAMES_MAX = 20000
ECHO_NAME_LOOKUPS = 12      # one-by-one lookups (collections, keywords) per answer
_BATCHED = NATIVE_ENTITY_TYPES - {"keywords"}


def _batch_names(entity_ids: List[str]) -> Optional[Dict[str, str]]:
    """Names for `type/ID` keys, one query per index; None when they can't be routed."""
    from query_translation.analytics import _id_names
    full = {f"https://openalex.org/{i.split('/', 1)[1].upper()}": i for i in entity_ids}
    try:
        got = _id_names(list(full), "default")
    except Exception:
        return None
    return None if got is None else {full[k]: v for k, v in got.items() if k in full and v}


def _remember(entity_id: str, name: str):
    _ECHO_NAMES[entity_id] = name
    while len(_ECHO_NAMES) > _ECHO_NAMES_MAX:
        _ECHO_NAMES.popitem(last=False)


def echo_name_resolver(oqo: OQO):
    """An engine resolver for `x_new_oql` on the execute path. Only the core renderer
    gets it, and `_link` ignores misses, so a miss is never a `[no entity found]` note."""
    from query_translation.oql_core import render_core
    from query_translation.oql_renderer import make_engine_resolver
    wanted: List[str] = []
    try:
        render_core(oqo, make_engine_resolver(lambda i: wanted.append(i), entity=oqo.get_rows))
    except Exception:  # noqa: BLE001 (names are decoration)
        pass
    names: Dict[str, Optional[str]] = {}
    fresh = []
    for i in dict.fromkeys(wanted):
        if i in _ECHO_NAMES:
            _ECHO_NAMES.move_to_end(i)
            names[i] = _ECHO_NAMES[i]
        elif "/" in i and i.split("/", 1)[0] in NATIVE_ENTITY_TYPES | {"collections"}:
            fresh.append(i)
    batch = [i for i in fresh if i.split("/", 1)[0] in _BATCHED]
    got = _batch_names(batch) if batch else {}
    one_by_one = [i for i in fresh if i not in batch] + (batch if got is None else [])
    for i, name in (got or {}).items():
        names[i] = name
        _remember(i, name)
    for i in one_by_one[:ECHO_NAME_LOOKUPS]:
        name = safe_get_display_name(i)
        names[i] = name
        if name and not i.startswith("collections/"):
            _remember(i, name)
    return make_engine_resolver(names.get, entity=oqo.get_rows)


def build_x_query(
    oqo: OQO,
    entity_resolver: Optional[Callable[[str], Optional[str]]] = None,
    sort_operands: bool = True,
    name_new_form: bool = False,
) -> dict:
    """Build the private `meta.x_query` triple {oql, oqo, url} (oxjob #373).

    The canonical multi-form representation of the executed query:
      - oql: re-rendered canonical OQL (round-trips: re-parsing it yields `oqo`)
      - oqo: the canonical structured query object the client hydrates from
      - url: the OXURL (`/works?filter=…`) form, or None when the OQO isn't
             URL-expressible (nested boolean trees, multi-dim group_by) — the URL
             syntax is a lossy subset of OQO, so this is null, never a 500.

    `sort_operands` (charter decision 30, #363) controls whether commutative
    operands — top-level `filter_rows` and the members of every `any (…)` / `all (…)`
    value bag — are alphabetically sorted. The OQL/builder **execute** path passes
    `sort_operands=False` so the user's authored order is HONORED end-to-end: the
    SERP rebuilds `?oql=` from this `x_query`, so a sort here silently reorders the
    user's values (e.g. `has any (c, b, a)` → `(a, b, c)`) — a spec violation (#475).
    The legacy-URL / per-entity path keeps the default sort (machine-shaped input).
    All the OTHER canonical transforms (NNF, flatten/hoist, column-id collapse,
    redundant-default-sort drop) run regardless of this flag.

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
    canonical = canonicalize_oqo(oqo, sort_operands=sort_operands)

    url_form = None
    try:
        components = render_oqo_to_url(canonical)
        # The sort is part of the query (Jason 2026-10-12, oxjob #1555; reverses #661 for
        # sort): it rides in the URL form. `select` stays view state (a sticky column
        # preference, the #471 leak class); paging stays: classic sibling params.
        components.pop("select", None)
        url_form = _components_to_oxurl(canonical.get_rows, components)
    except URLRenderError:
        # Not URL-expressible (e.g. nested boolean tree). url stays None; the
        # client treats null as an "advanced query" it can't render as chips.
        pass

    oql_form = None
    oql_unavailable = None
    try:
        style = effective_style()
        if style == "core":
            from query_translation.oql_core import render_core
            oql_form = render_core(canonical)
        if oql_form is not None:
            pass
        elif entity_resolver is not None:
            oql_form = render_oqo_to_oql(canonical, entity_resolver=entity_resolver)
        else:
            # Executed-query path (decision 14): bare-ID canonical OQL, no resolver
            # object at all — see the docstring for why wrapping None is a bug.
            # core's fallback is the pipeline text (oql_lang._pipeline_style)
            oql_form = oql_lang.render(canonical, resolver=None, style=style)
    except OQLError as e:
        # No honest OQL form for this query (classic fuzzy `term~N`, oxjob #865).
        # Mirror the url leg: omit rather than echo OQL that means something
        # else, and say why.
        oql_unavailable = e.message

    # The echoed OQO conforms to the PUBLIC spec (schema v1.6): which rows, in what
    # order (`sort_by` joined the query, Jason 2026-10-12, oxjob #1555; it decides rank
    # vs breakdown and binds the website's sort dropdown to the OQL). The view params
    # (#661) are stripped here, at the single echo boundary.
    oqo_dict = canonical.to_dict()
    for view_key in ("select", "page", "per_page", "cursor"):
        oqo_dict.pop(view_key, None)

    x_new = None
    style = effective_style()
    if name_new_form:
        # the OQL execute path names its entities in the new form, as /query and /validate
        # do (oxjob #1555; the website projects this echo into its URL, #1744)
        from query_translation.oql_core import render_core
        try:
            x_new = render_core(canonical, echo_name_resolver(canonical))
        except OQLError:
            pass
    if x_new is None:
        # no core form: the pipeline text, which `oql` already is in the core and pipeline styles
        x_new = oql_form if style == "core" or (name_new_form and style == "pipeline") \
            else new_oql(canonical)
    out = {
        "oql": oql_form,
        # the new form beside the old until the flip (oxjob #1555, Jason 2026-10-13)
        "x_new_oql": x_new,
        "oqo": oqo_dict,
        "url": url_form,
    }
    if oql_unavailable is not None:
        out["oql_unavailable"] = oql_unavailable
    return out
