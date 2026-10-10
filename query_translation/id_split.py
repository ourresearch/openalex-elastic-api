"""Big id filters, split side by side (oxjob #1617), and the parallel helpers walks share.

A set in parentheses becomes a `terms` filter on its ids (walk_exec.IdSet). ES spends
most of a request on a big one: the 304,923 works cited by KU's 2024+ works cost
1.6 s to apply in one request and 3.4 s with a split by source, every time the filter
goes out. The same filter cut into 8 disjoint pieces, 8 requests in flight, took 1.3 s
for the split in all (works-v38, 72 shards; #1617 EXPLORE.md "Where the time goes").

The pieces' answers add up exactly when each piece answers in full, so a request is
split only when every aggregation in it merges exactly: counts, sums, mins, maxes,
filters, and one level of `terms` on a field a work holds once (a piece of PIECE_IDS
works then lists at most PIECE_IDS keys, under PIECE_KEYS, so it answers in full). A
`cardinality` becomes the number of distinct keys the pieces list: exact, not ES's
estimate. Anything else (hits, sorts, means, medians, nested `terms`, fields a work
holds many of) runs as one request, as before. A call already running in one of
_pmap's threads isn't split, so no more than INFLIGHT calls are in flight.
"""
import math
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List, Optional, Tuple

INFLIGHT = 8             # calls in flight (measured safe on production, 2026-10-03)
SPLIT_MIN_IDS = 40_000   # below this the filter is cheap (100K author ids: 0.9 s)
PIECE_IDS = 40_000       # about this many ids a piece
PIECE_KEYS = 65_000      # keys one terms request lists (under the 65,536-bucket cap)

# Works fields a work holds at most once. shortcut: a prefix list, not the registry;
# a field missing here only runs whole (as before), never wrong.
SINGLE_VALUED = ("publication_year", "publication_date", "type", "language",
                 "primary_location.", "primary_topic.", "open_access.", "best_oa_location.",
                 "cited_by_count", "fwci", "citation_normalized_percentile.", "is_", "has_")

_METRICS = ("value_count", "sum", "min", "max")
_local = threading.local()


def _pmap(fn, items, inflight=INFLIGHT):
    """`fn` over `items`, up to `inflight` at a time, in order."""
    items = list(items)
    if len(items) <= 1:
        return [fn(x) for x in items]

    def in_pool(x):
        _local.in_pool = True
        return fn(x)
    with ThreadPoolExecutor(min(inflight, len(items))) as ex:
        return list(ex.map(in_pool, items))


def _terms(field: str, ids: List) -> dict:
    """`field` holds any of `ids`, chunked under the 65,536-terms clause cap."""
    from core.fields import TERMS_CHUNK
    if not ids:
        return {"bool": {"must_not": [{"match_all": {}}]}}
    chunks = [ids[i:i + TERMS_CHUNK] for i in range(0, len(ids), TERMS_CHUNK)]
    if len(chunks) == 1:
        return {"terms": {field: chunks[0]}}
    return {"bool": {"should": [{"terms": {field: c}} for c in chunks],
                     "minimum_should_match": 1}}


def piece_full(agg: dict) -> bool:
    """A terms answer that may have left keys out."""
    return bool(agg.get("sum_other_doc_count")) or len(agg.get("buckets") or []) >= PIECE_KEYS


class Whole(Exception):
    """The pieces can't be merged exactly: run the request whole."""


def _kind_sub(a: dict) -> Tuple[str, Dict[str, dict]]:
    """(an aggregation's type, its sub-aggregations)."""
    return next(k for k in a if k not in ("aggs", "meta")), a.get("aggs") or {}


def _terms_size(f: dict) -> Optional[Tuple[str, int]]:
    """(field, number of values) of `{"terms": {field: [...]}}` or of an OR of such
    clauses on one field (the shape _terms and core.fields.any_of_terms build)."""
    if set(f) == {"terms"} and len(f["terms"]) == 1:
        field, values = next(iter(f["terms"].items()))
        return (field, len(values)) if isinstance(values, list) else None
    b = f.get("bool") if set(f) == {"bool"} else None
    if not b or set(b) - {"should", "minimum_should_match"} or b.get("minimum_should_match") != 1:
        return None
    parts = [_terms_size(s) for s in b.get("should") or []]
    if not parts or any(p is None for p in parts) or len({p[0] for p in parts}) != 1:
        return None
    return parts[0][0], sum(p[1] for p in parts)


def _values(f: dict) -> List:
    if "terms" in f:
        return next(iter(f["terms"].values()))
    return [v for s in f["bool"]["should"] for v in _values(s)]


def _and_clauses(q: dict, path=()):
    """Every clause ANDed into `q` (through nested bool filter/must), with its path."""
    b = q.get("bool") if set(q) == {"bool"} else None
    if not b or set(b) - {"filter", "must"}:
        return
    for key in ("filter", "must"):
        kids = b.get(key)
        for i, c in enumerate(kids if isinstance(kids, list) else [kids] if kids else []):
            yield path + (key, i), c
            yield from _and_clauses(c, path + (key, i))


def _replace(q: dict, path, new: dict) -> dict:
    """A copy of `q` with the clause at `path` replaced (copies only along the path)."""
    if not path:
        return new
    key, i = path[0], path[1]
    b = dict(q["bool"])
    kids = list(b[key] if isinstance(b[key], list) else [b[key]])
    kids[i] = _replace(kids[i], path[2:], new)
    b[key] = kids
    return {"bool": b}


def _id_filter(query: dict):
    """(path, clause, field, n) of the biggest terms filter ANDed into `query` with at
    least SPLIT_MIN_IDS values."""
    best = None
    for path, c in _and_clauses(query):
        found = _terms_size(c)
        if found and found[1] >= SPLIT_MIN_IDS and (best is None or found[1] > best[3]):
            best = (path, c, found[0], found[1])
    return best


def _sibling(aggs: Dict[str, dict], field: str) -> Optional[str]:
    """A `terms` in `aggs` listing every key of `field` (no include/exclude)."""
    for name, a in aggs.items():
        t = a.get("terms")
        if t and t.get("field") == field and not ({"include", "exclude"} & set(t)):
            return name
    return None


def _order(spec: dict) -> List[Tuple[str, str]]:
    order = spec.get("order") or [{"_count": "desc"}]
    order = [next(iter(o.items())) for o in (order if isinstance(order, list) else [order])]
    if not any(k == "_key" for k, _ in order):
        order.append(("_key", "asc"))   # ES breaks count ties by key
    return order


def _piece_aggs(aggs: Dict[str, dict], inside_terms: bool = False) -> Dict[str, dict]:
    """The aggregations a piece runs: every `terms` lists all its keys, a
    `cardinality` lists its keys (or reads a sibling `terms` on the same field);
    raises Whole for anything that doesn't merge exactly."""
    out = {}
    for name, a in aggs.items():
        kind, sub = _kind_sub(a)
        spec = a[kind]
        if kind in _METRICS:
            out[name] = {kind: spec}
        elif kind == "cardinality":
            if inside_terms or set(spec) - {"field", "precision_threshold"} \
                    or not spec["field"].startswith(SINGLE_VALUED):
                raise Whole()
            if _sibling(aggs, spec["field"]) is None:
                out[name] = {"terms": {"field": spec["field"], "size": PIECE_KEYS}}
        elif kind in ("filter", "filters", "missing"):
            out[name] = {kind: spec}
            if sub:
                out[name]["aggs"] = _piece_aggs(sub, inside_terms)
        elif kind == "terms":
            if inside_terms or set(spec) - {"field", "size", "shard_size", "include",
                                            "exclude", "order", "min_doc_count",
                                            "execution_hint"} \
                    or not spec["field"].startswith(SINGLE_VALUED) \
                    or (spec.get("min_doc_count") or 1) > 1:
                raise Whole()
            for key, _dir in _order(spec):
                if key not in ("_count", "_key") and _kind_sub(sub.get(key) or {"": 0})[0] \
                        not in _METRICS:
                    raise Whole()
            t = {k: v for k, v in spec.items() if k not in ("size", "shard_size", "order")}
            t["size"] = PIECE_KEYS
            out[name] = {"terms": t}
            if sub:
                out[name]["aggs"] = _piece_aggs(sub, True)
        else:
            raise Whole()
    return out


def plan(body: dict) -> Optional[List[dict]]:
    """The pieces of `body`, or None when it should run whole."""
    if body.get("size", 10) != 0 or set(body) - {"size", "query", "aggs", "track_total_hits"} \
            or getattr(_local, "in_pool", False):
        return None
    try:
        aggs = _piece_aggs(body.get("aggs") or {})
    except Whole:
        return None
    found = _id_filter(body.get("query") or {})
    if found is None:
        return None
    path, clause, field, n_ids = found
    n = min(INFLIGHT, math.ceil(n_ids / PIECE_IDS))
    ids = _values(clause)
    pieces = []
    for i in range(n):
        piece = {"size": 0, "query": _replace(body["query"], path, _terms(field, ids[i::n]))}
        if "track_total_hits" in body:
            piece["track_total_hits"] = body["track_total_hits"]
        if aggs:
            piece["aggs"] = aggs
        pieces.append(piece)
    return pieces


def _merge_aggs(spec: Dict[str, dict], results: List[dict]) -> dict:
    out, n_keys = {}, {}
    for name, a in spec.items():
        kind, sub = _kind_sub(a)
        if kind == "cardinality":
            continue   # after its sibling terms
        got = [r[name] for r in results]
        if kind in ("value_count", "sum"):
            out[name] = {"value": sum(g.get("value") or 0 for g in got)}
        elif kind in ("min", "max"):
            vals = [g["value"] for g in got if g.get("value") is not None]
            out[name] = {"value": (min if kind == "min" else max)(vals) if vals else None}
        elif kind in ("filter", "missing"):
            out[name] = {"doc_count": sum(g["doc_count"] for g in got), **_merge_aggs(sub, got)}
        elif kind == "filters":
            first = got[0]["buckets"]
            names = list(first) if isinstance(first, dict) else range(len(first))
            merged = {k: {"doc_count": sum(g["buckets"][k]["doc_count"] for g in got),
                          **_merge_aggs(sub, [g["buckets"][k] for g in got])} for k in names}
            out[name] = {"buckets": merged if isinstance(first, dict) else list(merged.values())}
        else:   # terms
            out[name], n_keys[name] = _merge_terms(a["terms"], sub, got)
    for name, a in spec.items():
        if "cardinality" not in a:
            continue
        sib = _sibling(spec, a["cardinality"]["field"])
        if sib is not None:
            out[name] = {"value": n_keys[sib]}
            continue
        keys = set()
        for r in results:
            if piece_full(r[name]):
                raise Whole()
            keys.update(b["key"] for b in r[name]["buckets"])
        out[name] = {"value": len(keys)}
    return out


def _merge_terms(spec: dict, sub: Dict[str, dict], got: List[dict]) -> Tuple[dict, int]:
    """(the merged terms answer cut to its size, how many keys there are in all)."""
    by_key: Dict = {}
    for g in got:
        if piece_full(g):
            raise Whole()
        for b in g["buckets"]:
            by_key.setdefault(b["key"], []).append(b)
    rows = [{"key": key, "doc_count": sum(b["doc_count"] for b in bs), "_bs": bs}
            for key, bs in by_key.items()]
    order = _order(spec)
    by_metric = any(k not in ("_count", "_key") for k, _ in order)

    def finish(r):
        bs = r.pop("_bs")
        if "key_as_string" in bs[0]:
            r["key_as_string"] = bs[0]["key_as_string"]
        r.update(_merge_aggs(sub, bs))
        return r
    if by_metric:   # the sort needs the merged metric; else merge only the kept rows
        rows = [finish(r) for r in rows]
    for key, direction in reversed(order):   # stable sorts, last key first
        desc = direction == "desc"
        if key == "_count":
            f = lambda r: r["doc_count"]
        elif key == "_key":
            f = lambda r: r["key"]
        else:
            # a group with no value sorts last either way (as ES does)
            def f(r, key=key, desc=desc):
                v = r[key]["value"]
                return (v is not None, v or 0) if desc else (v is None, v or 0)
        rows.sort(key=f, reverse=desc)
    size = spec.get("size", 10)
    kept = rows[:size] if by_metric else [finish(r) for r in rows[:size]]
    return ({"doc_count_error_upper_bound": 0,
             "sum_other_doc_count": sum(r["doc_count"] for r in rows[size:]),
             "buckets": kept}, len(rows))


def merge(body: dict, results: List[dict]) -> dict:
    """One response from the pieces' responses; raises Whole when inexact."""
    totals = [r["hits"]["total"] for r in results]
    out = {"took": max(r.get("took") or 0 for r in results), "timed_out": False,
           "hits": {"total": {"value": sum(t["value"] for t in totals),
                              "relation": "gte" if any(t.get("relation") == "gte" for t in totals)
                              else "eq"},
                    "max_score": None, "hits": []}}
    if body.get("aggs"):
        out["aggregations"] = _merge_aggs(body["aggs"], [r.get("aggregations") or {}
                                                         for r in results])
    return out


def search(run_one, body: dict) -> Optional[dict]:
    """Run `body` in pieces side by side through `run_one(piece_body)`; None when it
    should run whole."""
    pieces = plan(body)
    if pieces is None:
        return None
    try:
        return merge(body, _pmap(run_one, pieces))
    except Whole:
        return None
