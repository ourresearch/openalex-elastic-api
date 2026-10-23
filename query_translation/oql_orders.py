"""The order a query's rows come in, and the orders it can take, in OQL words (oxjob #1658).

The website's sort menu and the OQL text are two views of one order (Jason 2026-10-12/13):
picking an order rewrites the end of the sentence, and typing one moves the menu. So the
menu never keeps a word list of its own: its choices are the orders the editor offers after
a comma (`/parse-context`), each read back by the parser, so every choice carries the exact
`sort_by` it sets. The default is named (`oql_core.default_order_words`) but never written.
"""
from dataclasses import replace
from typing import Any, Dict, Optional, Tuple

from query_translation import oql_core as C
from query_translation.oql_lang import _BY_COLUMN
from query_translation.oqo import OQO, Measure


def _said(oqo: OQO) -> str:
    """The order words the sentence ends with ("" for the default). Raises NotCore when
    OQL has no words for the order."""
    if oqo.group_by:
        text, _ = C._table_order(oqo, list(oqo.calculate) or [Measure("count")])
    else:
        text = C._order_text(oqo.sort_by, oqo.get_rows, C._has_search(oqo.filter_rows))
    return text[2:] if text.startswith(", ") else text


def describe_order(oqo: OQO) -> Tuple[Optional[str], bool]:
    """(words, is_default) for the order the rows come in: the sentence's own words
    (`newest first`), or the default's name with is_default (the text writes nothing).
    (None, False) for one number (no order) or an order OQL has no words for."""
    if not oqo.group_by and oqo.calculate:
        return None, False
    try:
        said = _said(oqo)
    except C.NotCore:
        return None, False
    return (said, False) if said else (C.default_order_words(oqo), True)


def _is_id_order(oqo: OQO) -> bool:
    """A sort by an ID string (`in institution ID order`): no use to people in a menu."""
    s = oqo.sort_by[0]
    if oqo.group_by:
        col = oqo.group_by[0].column_id
        return s.column_id == "key" and col != "publication_year" \
            and not C.key_order_is_alphabetical(col)
    fld = _BY_COLUMN.get(s.column_id)
    return fld is not None and fld.kind == "id"


def _order_slot(text: str) -> Tuple[str, str]:
    """`text` cut where its order goes: before a table's `Show ...` / `Only ...` sentences
    (split the parser's way, with links and quotes held aside)."""
    t = C._Text(text)
    first, *rest = C._split_sentences(t)
    return t.restore(first), "".join(f". {t.restore(p)}" for p in rest) + ("." if rest else "")


def orders_for(oql: str) -> Dict[str, Any]:
    """The menu for one query: {order, order_default, options: [{words, sort_by, default?}]}.
    The default comes first with an empty `sort_by` (the engine's default; the text says
    nothing). Not offered: ID orders, and orders that would add a column (a thing's own
    field the table doesn't show): a sort never changes what the table shows (#1555,
    2026-10-22). Raises the parser's error for OQL that doesn't parse."""
    from query_translation.oql_context import parse_context
    from query_translation.oql_parser import parse_either
    from query_translation.oqo_canonicalizer import canonicalize_oqo

    oqo = canonicalize_oqo(parse_either(oql), sort_operands=False)
    words, is_default = describe_order(oqo)
    out: Dict[str, Any] = {"order": words, "order_default": is_default, "options": []}
    default = C.default_order_words(oqo)
    if default is None:
        return out
    out["options"] = [{"words": default, "sort_by": [], "default": True}]
    base_oqo = replace(oqo, sort_by=[])
    base = C.render_core(base_oqo)
    if base is None:
        return out
    head, tail = _order_slot(base)
    q = head + ", "
    seen = {default}
    for s in (parse_context(q + tail, len(q)).get("context") or {}).get("suggestions") or []:
        if s.get("kind") != "order" or s["value"] in seen:
            continue
        seen.add(s["value"])
        try:
            got = canonicalize_oqo(parse_either(q + s["value"] + tail), sort_operands=False)
        except Exception:  # noqa: BLE001 (a suggestion that doesn't parse isn't offered)
            continue
        if got.calculate != base_oqo.calculate or describe_order(got)[1] or _is_id_order(got):
            continue      # adds a column; the default under another name; an ID order
        out["options"].append({"words": s["value"], "sort_by": [x.to_dict() for x in got.sort_by]})
    return out
