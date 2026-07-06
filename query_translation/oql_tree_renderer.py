"""
OQL Tree Renderer — OQO -> (canonical OQL string, oql_render tree).

As of oxjob #376 this is a thin wrapper over the ONE OQL engine
(`query_translation.oql_lang`). The engine's `render_tree()` builds both the
string and the `oql_render` tree from a single walk, so the invariant
`stringify(oql_render) == oql` (Invariant A) holds by construction. Name
resolution is adapted from prod's `entity_resolver(entity_id)` surface via
`oql_renderer.make_engine_resolver`.

See query_translation/oql_lang.py and query_translation/oql_render_tree.py.
"""

from typing import Optional, Callable, Tuple

from query_translation.oqo import OQO
from query_translation import oql_lang
from query_translation.oql_render_tree import OQLRenderTree
from query_translation.oql_renderer import make_engine_resolver


def render_oqo_to_oql_and_tree(
    oqo: OQO,
    entity_resolver: Optional[Callable[[str], Optional[str]]] = None,
    engine_resolver: Optional[Callable[[str, str], Optional[str]]] = None,
) -> Tuple[str, OQLRenderTree]:
    """Render an OQO to both canonical OQL and its oql_render tree.

    Args:
        oqo: the OQO to render
        entity_resolver: optional `entity_id -> display name` callable
        engine_resolver: optional pre-built `(value, column_id) -> name` engine
            resolver; pass this to share one lookup cache across several renders
            of the same request (takes precedence over `entity_resolver`)

    Returns:
        (oql_string, oql_render_tree) — `stringify(tree) == oql_string`.
    """
    resolver = engine_resolver or make_engine_resolver(
        entity_resolver, entity=oqo.get_rows)
    return oql_lang.render_tree(oqo, resolver=resolver)
