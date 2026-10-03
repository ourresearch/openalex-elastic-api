"""Pipeline results as a download (oxjob #1530; spec from #1536, Jason 2026-10-03):
a zip of `groups.csv` (one row per innermost group, ancestors repeated), `totals.csv`
(the total row and its breakdown, and each outer group's own row: they don't sum
from the leaves) and `query.oql` (the query, when it ran, how many works, the price).
Headers are OQL words: each split's (`institution`, plus `institution id` for
splits by things with ids) and each calculation's (`meta.measures[].oql`)."""
import csv
import io
import re
import zipfile
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

from query_translation.oqo import OQO, GroupBy

KINDS = ("column", "values", "searches", "bins", "conditions")


def split_meta(g: GroupBy, entity: str) -> dict:
    """One split as the website and the CSV headers name it."""
    from query_translation.oql_lang import _group_entity, _oql_field
    name = _oql_field(g.column_id)[0] if g.column_id else ""
    if g.conditions is not None:
        kind, oql = "conditions", "condition"
    elif g.bins is not None:
        kind, oql = "bins", f"{name} bins"
    elif g.values is not None and g.column_id.endswith(".search"):
        kind, oql = "searches", f"{name} search"
    elif g.values is not None:
        kind, oql = "values", name
    else:
        kind, oql = "column", name
    has_ids = kind in ("column", "values") and _group_entity(g, entity) is not None
    return {"oql": oql, "column_id": g.column_id, "kind": kind, "has_ids": has_ids}


def _short_id(key) -> str:
    return str(key).rstrip("/").rsplit("/", 1)[-1]


def _cell(v) -> str:
    if v is None:
        return ""
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v)


def _header(splits: List[dict], measures: List[dict]) -> List[str]:
    cols: List[str] = []
    for s in splits:
        cols.append(s["oql"])
        if s["has_ids"]:
            cols.append(f"{s['oql']} id")
    return cols + [m["oql"] for m in measures]


def _cells(splits: List[dict], path: List[Optional[dict]], row: dict,
           measures: List[dict]) -> List[str]:
    """`path[i]` is the row at split i on the way down (None for an empty cell)."""
    out: List[str] = []
    for s, at in zip(splits, path):
        out.append(_cell(at["key_display_name"]) if at else "")
        if s["has_ids"]:
            out.append(_short_id(at["key"]) if at else "")
    return out + [_cell(row.get(m["key"])) for m in measures]


def _leaves(rows: List[dict], depth: int, n: int, path: List[dict]):
    for r in rows:
        p = path + [r]
        if depth + 1 < n:
            yield from _leaves(r.get("groups") or [], depth + 1, n, p)
        else:
            yield p, r


def _all_rows(rows: List[dict], depth: int, n: int, path: List[Optional[dict]]):
    for r in rows:
        p = path + [r]
        yield p, r
        if depth + 1 < n:
            yield from _all_rows(r.get("groups") or [], depth + 1, n, p)


def _subtotals(rows: List[dict], depth: int, n: int, path: List[dict]):
    """Each non-innermost group's own row."""
    for r in rows:
        if depth + 1 < n:
            yield path + [r], r
            yield from _subtotals(r.get("groups") or [], depth + 1, n, path + [r])


def _csv(header: List[str], rows: List[List[str]]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(header)
    w.writerows(rows)
    return buf.getvalue()


def filename(oql_text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", oql_text.lower()).strip("-")[:80].strip("-")
    return f"openalex-{slug or 'query'}.zip"


def build_zip(oqo: OQO, body: dict, cost: dict, oql_text: str,
              cap_note: Optional[str] = None) -> Tuple[bytes, str]:
    meta = body["meta"]
    splits = meta.get("splits") or [split_meta(g, oqo.get_rows) for g in oqo.group_by]
    measures = meta["measures"]
    n = len(splits)
    pad = lambda p: p + [None] * (n - len(p))  # noqa: E731

    groups = [_cells(splits, pad(p), r, measures)
              for p, r in _leaves(body.get("group_by") or [], 0, n, [])] if n else []

    total = body["total"]
    totals = [["total"] + _cells(splits, [None] * n, total, measures)]
    if n > 1:
        totals += [["total"] + _cells(splits, pad([None] + p), r, measures)
                   for p, r in _all_rows(total.get("groups") or [], 1, n, [])]
        totals += [["subtotal"] + _cells(splits, pad(p), r, measures)
                   for p, r in _subtotals(body.get("group_by") or [], 0, n, [])]

    header = _header(splits, measures)
    run_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    noun = oqo.get_rows.replace("-", " ")
    notes = [f"# run: {run_at}",
             f"# {noun}: {total.get('count')}",
             f"# price: {cost['credits']} credit{'s' if cost['credits'] != 1 else ''} "
             f"(${cost['usd']})"]
    if cap_note:
        notes.append(f"# {cap_note}")
    query = oql_text.rstrip() + "\n\n" + "\n".join(notes) + "\n"

    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("groups.csv", _csv(header, groups))
        z.writestr("totals.csv", _csv(["row"] + header, totals))
        z.writestr("query.oql", query)
    return out.getvalue(), filename(" ".join(oql_text.split()))
