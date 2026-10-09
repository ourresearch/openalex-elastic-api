"""Pipeline results as flat CSV downloads (oxjob #1550, Jason 2026-10-05/08: "JSON wants
to nest. CSV wants to be flat."; a plain CSV whenever there is one file, a zip only when
a summary really has several), replacing #1530's zip of groups.csv/totals.csv/query.oql:

- the groups (`table=groups`, the default): ONE CSV, one row per innermost group, a
  column per split (ancestors repeated), so every row stands on its own. With no split
  it is the one row for the whole set.
- the summary (`table=summary`): one CSV per table, each computed from the works (never
  summed or averaged from group rows): `all-works.csv` (the whole set, one row) and,
  with two or more splits, `by-<split>.csv` for each split's groups on their own (the
  pivot tables). One file goes out as a plain CSV, several as a zip.

Headers are OQL words: each split's (`institution`, plus `institution id` for splits
by things with ids) and each calculation's (`meta.measures[].oql`); repeated names get
a number (`condition`, `condition 2`). Plain UTF-8 with no byte-order mark and values
as they are, like the works export (users-api formats/csv.py)."""
import csv
import io
import re
import zipfile
from typing import List, Optional, Tuple

from query_translation.oqo import OQO, GroupBy

TABLES = ("groups", "summary")
# measures with no whole-set value: a group's share of its parent, a group's own field
NO_WHOLE_SET = ("percent_of_those", "value")


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


def _label(row: dict) -> str:
    name = row.get("key_display_name")
    return _cell(row.get("key") if name is None or name == "" else name)


def _unique(names: List[str]) -> List[str]:
    """Header names, numbered when repeated: two condition splits -> condition, condition 2."""
    seen: dict = {}
    out = []
    for n in names:
        n = n or "group"
        seen[n] = seen.get(n, 0) + 1
        out.append(n if seen[n] == 1 else f"{n} {seen[n]}")
    return out


def _split_cols(s: dict) -> List[str]:
    return [s["oql"] or "group"] + ([f"{s['oql']} id"] if s.get("has_ids") else [])


def _split_cells(s: dict, at: Optional[dict]) -> List[str]:
    if at is None:
        return [""] * (2 if s.get("has_ids") else 1)
    return [_label(at)] + ([_short_id(at.get("key"))] if s.get("has_ids") else [])


def _leaves(rows: List[dict], depth: int, n: int, path: List[dict]):
    for r in rows or []:
        p = path + [r]
        if depth + 1 < n:
            yield from _leaves(r.get("groups") or [], depth + 1, n, p)
        else:
            yield p, r


def _csv(header: List[str], rows: List[List[str]]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(_unique(header))
    w.writerows(rows)
    return buf.getvalue()


def _splits(body: dict, oqo: OQO) -> List[dict]:
    """`meta.splits`, or derived from the query when a response doesn't carry them."""
    return body.get("meta", {}).get("splits") or [split_meta(g, oqo.get_rows) for g in oqo.group_by]


def _whole_set(measures: List[dict]) -> List[dict]:
    return [m for m in measures if m.get("measure") not in NO_WHOLE_SET]


def _all_row(body: dict) -> dict:
    return (body.get("summary") or {}).get("all") or {}


def groups_csv(body: dict, oqo: OQO) -> str:
    """The groups table, flat. A calculation with no split is one row: the whole set."""
    measures = body.get("meta", {}).get("measures") or []
    splits = _splits(body, oqo)
    if not splits:
        ms = _whole_set(measures)
        return _csv([m["oql"] for m in ms], [[_cell(_all_row(body).get(m["key"])) for m in ms]])
    header = [c for s in splits for c in _split_cols(s)] + [m["oql"] for m in measures]
    rows = []
    for path, leaf in _leaves(body.get("group_by") or [], 0, len(splits), []):
        cells = [c for s, at in zip(splits, path) for c in _split_cells(s, at)]
        rows.append(cells + [_cell(leaf.get(m["key"])) for m in measures])
    return _csv(header, rows)


def _file_slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")


def summary_files(body: dict, oqo: OQO) -> List[Tuple[str, str]]:
    """[(file name, CSV text)]: all-works.csv, then by-<split>.csv for each split on its
    own (only with two or more splits; one split's groups are the groups table)."""
    measures = body.get("meta", {}).get("measures") or []
    splits = _splits(body, oqo)
    entity = _file_slug(oqo.get_rows) or "works"
    ms = _whole_set(measures)
    files = [(f"all-{entity}.csv",
              _csv([m["oql"] for m in ms], [[_cell(_all_row(body).get(m["key"])) for m in ms]]))]
    parts = (body.get("summary") or {}).get("splits") or []
    if len(splits) < 2:
        return files
    used = {files[0][0]}
    for i, s in enumerate(splits):
        part = (parts[i] if i < len(parts) else None) or {}
        groups = part.get("groups") or []
        # a group's own field shows only where the groups have it (each author's h-index
        # in by-author, not by-year)
        cols = [m for m in measures
                if m.get("measure") != "value" or any(g.get(m["key"]) is not None for g in groups)]
        rows = [_split_cells(s, g) + [_cell(g.get(m["key"])) for m in cols] for g in groups]
        base = f"by-{_file_slug(s['oql']) or f'split-{i + 1}'}"
        name, k = f"{base}.csv", 1
        while name in used:
            k += 1
            name = f"{base}-{k}.csv"
        used.add(name)
        files.append((name, _csv(_split_cols(s) + [m["oql"] for m in cols], rows)))
    return files


def filename(oql_text: str, suffix: str = "", ext: str = "csv") -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", " ".join((oql_text or "").split()).lower())
    slug = slug.strip("-")[:80].strip("-")
    return f"openalex-{slug or 'query'}{suffix}.{ext}"


def data_rows(text: str) -> int:
    """Rows below the header (a quoted value may hold a line break, so parse, don't count
    lines)."""
    return max(0, sum(1 for _ in csv.reader(io.StringIO(text))) - 1)


def build_download(body: dict, oqo: OQO, oql_text: str, table: str = "groups"
                   ) -> Tuple[bytes, str, str, int]:
    """(content, file name, mimetype, rows) for one download: the groups CSV, or the
    summary as one CSV or, when it has several tables, a zip of them. `rows` (every data
    row in every file) prices it."""
    if table == "summary":
        files = summary_files(body, oqo)
        rows = sum(data_rows(text) for _, text in files)
        if len(files) == 1:
            return (files[0][1].encode("utf-8"), filename(oql_text, "-summary"),
                    "text/csv", rows)
        out = io.BytesIO()
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
            for name, text in files:
                z.writestr(name, text)
        return (out.getvalue(), filename(oql_text, "-summary", "zip"), "application/zip",
                rows)
    text = groups_csv(body, oqo)
    return text.encode("utf-8"), filename(oql_text), "text/csv", data_rows(text)
