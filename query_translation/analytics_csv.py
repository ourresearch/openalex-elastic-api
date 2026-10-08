"""Pipeline results as two flat CSVs (oxjob #1550, Jason 2026-10-05: "JSON wants to
nest. CSV wants to be flat."), replacing #1530's zip:

- the groups table: one row per innermost group, a column per split (ancestors
  repeated), so every row stands on its own and sorts on its own;
- the summary table: the whole set, then each split's groups on their own, all
  computed from the works (never summed or averaged from group rows). Its first
  column says what the row summarizes (`all works`, `year`); the split columns it
  doesn't break down are empty.

Headers are OQL words: each split's (`institution`, plus `institution id` for
splits by things with ids) and each calculation's (`meta.measures[].oql`)."""
import csv
import io
import re
from typing import List, Optional

from query_translation.oqo import GroupBy

KINDS = ("column", "values", "searches", "bins", "conditions")
TABLES = ("groups", "summary")


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


def _csv(header: List[str], rows: List[List[str]]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(header)
    w.writerows(rows)
    return buf.getvalue()


def groups_csv(body: dict) -> str:
    """The groups table, flat. A calculation with no split is one row: the whole set."""
    meta = body["meta"]
    splits, measures = meta["splits"], meta["measures"]
    n = len(splits)
    if not n:
        return _csv(_header([], measures), [_cells([], [], body["summary"]["all"], measures)])
    rows = [_cells(splits, p, r, measures) for p, r in _leaves(body.get("group_by") or [], 0, n, [])]
    return _csv(_header(splits, measures), rows)


def summary_csv(body: dict, entity: str) -> str:
    """The summary table: the whole set, then each split's groups on their own."""
    meta = body["meta"]
    splits, measures = meta["splits"], meta["measures"]
    summary = body["summary"]
    n = len(splits)
    rows = [[f"all {entity.replace('-', ' ')}"]
            + _cells(splits, [None] * n, summary["all"], measures)]
    for i, part in enumerate(summary.get("splits") or []):
        for r in part["groups"]:
            path = [r if j == i else None for j in range(n)]
            rows.append([splits[i]["oql"]] + _cells(splits, path, r, measures))
    return _csv(["summary of"] + _header(splits, measures), rows)


def filename(oql_text: str, table: str = "groups") -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", oql_text.lower()).strip("-")[:80].strip("-")
    suffix = "-summary" if table == "summary" else ""
    return f"openalex-{slug or 'query'}{suffix}.csv"


def build_csv(body: dict, entity: str, oql_text: str, table: str = "groups"):
    """(text, file name) for one of the two tables."""
    text = summary_csv(body, entity) if table == "summary" else groups_csv(body)
    return text, filename(" ".join(oql_text.split()), table)
