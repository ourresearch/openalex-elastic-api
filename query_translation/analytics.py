"""Runs the pipeline language's analytics (oxjob #1530; design: the job's work/DESIGN.md).

An OQO that splits by listed values, searches, bins or conditions, filters its groups,
or calculates anything runs here instead of the legacy group-by path. Every split and
every measure goes into ONE Elasticsearch request:

    split by a column           terms (a page of groups; all groups, up to a guard,
                                when nested)
    listed values, searches,    filters (every group listed, empty ones as 0)
    conditions, yes/no
    bins                        range (`at`) or histogram (`of`)
    measures                    avg / percentiles 50 / sum / min / max / a filter for
                                `percent`, at every level and at the root (the summary's
                                whole-set row)
    each inner split alone      the same split at the root, over the whole set (the
                                summary, #1550)
    group filters on measures   min_doc_count + bucket_selector

Group filters on a group's own fields (an author's h-index), `co-author` and
`collaborator` need one lookup call first (measured in #1512: 2 calls, 3-6 s after a
count filter); their key sets become the terms `include` / `exclude`.

Every ES call gets the time left of the query's deadline (11 s, under gunicorn's 12; Jason 2026-10-03); a call
that runs out is abandoned (closing the connection cancels the search in ES) and the
query answers with a message saying how to narrow it.
"""
import json
import os
import re
import time
from dataclasses import dataclass, field, replace
from typing import Any, Dict, List, Optional, Tuple

from elasticsearch.exceptions import ConnectionTimeout, TransportError
from elasticsearch_dsl import Q, Search

import settings
from core.exceptions import APIQueryParamsError
from core.preference import clean_preference
from query_translation.analytics_csv import split_meta
from query_translation.oqo import (
    OQO, AffiliationFilter, BranchFilter, GroupBy, LeafFilter, Measure, MeasureFilter)

# Limits (Jason, 2026-10-03; #1512 measured the costs).
# The engine cancels anything still running at 11 s: Jason's ceiling is 15, but
# gunicorn kills the worker at 12 (Procfile --timeout 12, #521), which would end the
# request with no message (found by #1535). The env var exists for tests that need a
# short deadline.
QUERY_DEADLINE_S = float(os.environ.get("OQL_QUERY_DEADLINE_S", "11"))
MAX_LEVEL_GROUPS = 10_000      # a nested split returns at most this many groups per split
MAX_RESPONSE_BUCKETS = 65_536  # ES search.max_buckets
FILTERED_CANDIDATES = 20_000   # a single split with a group filter checks this many groups
LOOKUP_LIMIT = 60_000          # own-field lookups list at most this many ids
# the works side of a group filter (oxjob #1555): the groups the works have, listed and
# checked in their records side by side at about 36,000 a second (walk_exec's measure)
WORKS_SIDE_LIMIT = 250_000
# an author's record with years is checked in its _source; prolific authors' records are
# long (9,401 UBC authors with h-index > 50: 45-68 MB, 5-10 s), so the own side checks at
# most this many candidates (the works side checks only those that have the place)
RECORD_CHECK_LIMIT = 5_000
DEFAULT_PER_PAGE = 200
MAX_PAGE_DEPTH = 10_000        # page x per_page on a single split
CSV_PAGE_GROUPS = 10_000       # groups in one page of an export (format=csv with a cursor, #1550)
ROWS_PER_PRICE = 100           # an export costs the query's price per 100 rows, like works (#1550)
ID_PREFIX = "https://openalex.org/"


class AnalyticsError(APIQueryParamsError):
    """A loud, fixable refusal: `code`, a message and the fix."""

    def __init__(self, code: str, message: str, fix: str, status: int = 400):
        super().__init__(f"{message} {fix}")
        self.code = code
        self.message = message
        self.fix = fix
        self.status = status

    def to_dict(self):
        return {"error": self.code, "message": self.message, "fix": self.fix}


class Deadline:
    """The query's time budget across its ES calls."""

    def __init__(self, seconds: float = QUERY_DEADLINE_S):
        self.start = time.monotonic()
        self.end = self.start + seconds
        self.calls = 0
        self.log: List[dict] = []     # one entry per ES call: what, ms since start
        self._last = self.start

    def remaining(self) -> float:
        return self.end - time.monotonic()

    def elapsed_ms(self) -> int:
        return int((time.monotonic() - self.start) * 1000)

    def timeout(self, what: str) -> float:
        """The request timeout for the next ES call; logs the step."""
        left = self.remaining()
        if left <= 0.25:
            raise too_slow(what)
        self.calls += 1
        self.mark(what)
        return left

    def mark(self, what: str):
        self.log.append({"step": what, "at_ms": self.elapsed_ms()})


def say_seconds(s: float) -> str:
    """`14 seconds`, `about 3 minutes`, `about 13 days`."""
    for unit, size in (("day", 86400), ("hour", 3600), ("minute", 60)):
        if s >= 2 * size:
            n = round(s / size)
            return f"about {n:,} {unit}s"
    n = round(s)
    return f"{n} second" if n == 1 else f"{n} seconds"


def count_fix(lv: Optional["Level"] = None, n: int = 10) -> str:
    """A count filter as the echo writes it (oxjob #1555): thing-first for a split by a
    thing, else the group filter."""
    from query_translation.oql_lang import THING_BY_COLUMN, THING_VERBS
    thing = THING_BY_COLUMN.get(lv.column_id) if lv is not None and lv.column_id else None
    if thing:
        return f"get {thing} {THING_VERBS[thing]} more than {n} works where ..."
    return f"... where count of those works is above {n}"


def too_slow(what: str) -> AnalyticsError:
    return AnalyticsError(
        "query_too_slow",
        f"This query ran past the {int(QUERY_DEADLINE_S)}-second limit while {what}, "
        f"so it was stopped.",
        "Narrow the starting set (a shorter year range, a smaller institution or topic), "
        f"add a count filter ({count_fix()}), or split it into several queries.")


# ---------------------------------------------------------------------------
# Measures
# ---------------------------------------------------------------------------
def _es_number_field(fields_dict, column_id: str) -> str:
    from core.utils import get_field
    f = get_field(fields_dict, column_id)
    return f.es_field().replace("__", ".")   # raw agg bodies need the dotted path


def _true_query(fields_dict, column_id: str):
    """The field's own query for `true` (yes/no columns)."""
    import copy
    from core.utils import get_field
    f = copy.copy(get_field(fields_dict, column_id))
    f.value = "true"
    return f.build_query()


def _measure_aggs(measures: List[Measure], fields_dict) -> Dict[str, dict]:
    from core.utils import get_field
    aggs = {}
    for m in measures:
        name = f"m_{m.key}"
        if m.measure in ("count", "percent_of_those", "value"):
            continue
        if m.measure == "percent":
            aggs[name] = {"filter": _true_query(fields_dict, m.column_id).to_dict()}
            continue
        es_field = _es_number_field(fields_dict, m.column_id)
        if m.measure == "median":
            aggs[name] = {"percentiles": {"field": es_field, "percents": [50]}}
        else:
            agg = {"mean": "avg", "sum": "sum", "min": "min", "max": "max"}[m.measure]
            aggs[name] = {agg: {"field": es_field}}
            if "Date" in type(get_field(fields_dict, m.column_id)).__name__:
                aggs[name][agg]["format"] = "yyyy-MM-dd"   # the earliest / latest date
    return aggs


def _round(v):
    if isinstance(v, float):
        return round(v, 4)
    return v


def _measure_value(m: Measure, bucket: dict, count: int, parent_count: Optional[int]):
    name = f"m_{m.key}"
    if m.measure == "count":
        return count
    if m.measure == "percent_of_those":
        if not parent_count:
            return None
        return _round(count * 100.0 / parent_count)
    agg = bucket.get(name)
    if agg is None:
        return None
    if m.measure == "percent":
        return _round(agg["doc_count"] * 100.0 / count) if count else None
    if m.measure == "median":
        return _round((agg.get("values") or {}).get("50.0"))
    if m.measure == "sum" and count == 0:
        return 0
    if "value_as_string" in agg and m.measure in ("min", "max"):
        return agg["value_as_string"] if agg.get("value") is not None else None
    return _round(agg.get("value"))


def _selector_path(m: Measure) -> Tuple[Dict[str, str], str]:
    """(buckets_path entries, painless expression) for a measure's value."""
    v = re.sub(r"[^A-Za-z0-9_]", "_", m.key)
    if m.measure == "count":
        return {"c": "_count"}, "params.c"
    if m.measure == "percent":
        return ({f"t_{v}": f"m_{m.key}>_count", "c": "_count"},
                f"(params.c > 0 ? params.t_{v} * 100.0 / params.c : 0)")
    if m.measure == "median":
        return {f"v_{v}": f"m_{m.key}[50.0]"}, f"params.v_{v}"
    return {f"v_{v}": f"m_{m.key}"}, f"params.v_{v}"


_PAINLESS_OPS = {">": ">", ">=": ">=", "<": "<", "<=": "<=", "is": "=="}


def _selector_script(node) -> Tuple[Dict[str, str], str]:
    """A measure-only group-filter tree as (buckets_path, painless boolean)."""
    if isinstance(node, MeasureFilter):
        paths, expr = _selector_path(Measure(node.measure, node.column_id))
        test = f"{expr} {_PAINLESS_OPS[node.operator]} {float(node.value)}"
        return paths, (f"!({test})" if node.is_negated else f"({test})")
    paths: Dict[str, str] = {}
    parts = []
    for c in node.filters:
        p, e = _selector_script(c)
        paths.update(p)
        parts.append(e)
    joined = (" && " if node.join == "and" else " || ").join(parts)
    return paths, (f"!({joined})" if node.is_negated else f"({joined})")


def _measures_in(node) -> List[Measure]:
    if isinstance(node, MeasureFilter):
        return [Measure(node.measure, node.column_id)]
    if isinstance(node, BranchFilter):
        out = []
        for c in node.filters:
            out.extend(_measures_in(c))
        return out
    return []


def _is_measure_only(node) -> bool:
    if isinstance(node, MeasureFilter):
        return True
    if isinstance(node, BranchFilter):
        return all(_is_measure_only(c) for c in node.filters)
    return False


def _has_measure(node) -> bool:
    if isinstance(node, MeasureFilter):
        return True
    if isinstance(node, BranchFilter):
        return any(_has_measure(c) for c in node.filters)
    return False


def _min_doc_count(where) -> int:
    """A top-level `count > N` / `count >= N` in the group filter becomes terms
    `min_doc_count`, which prunes candidates before the selector runs."""
    nodes = where.filters if (isinstance(where, BranchFilter) and where.join == "and"
                              and not where.is_negated) else [where]
    best = 1
    for n in nodes:
        if isinstance(n, MeasureFilter) and n.measure == "count" and not n.is_negated:
            if n.operator == ">":
                best = max(best, int(n.value) + 1)
            elif n.operator == ">=":
                best = max(best, int(-(-n.value // 1)))
    return best


def _count_floor_only(where) -> bool:
    """The group filter is only `count >` / `count >=`: terms min_doc_count applies it
    before the split is sized, so the split's first groups by count are exact."""
    if where is None:
        return False
    m_parts, k_parts = _split_where(where)
    return bool(m_parts) and not k_parts and all(
        isinstance(p, MeasureFilter) and p.measure == "count" and not p.is_negated
        and p.operator in (">", ">=") for p in m_parts)


def _filter_truncated(lv, aggs: dict) -> bool:
    """Did a filtered single split have more groups than it checked?"""
    if lv.kind != "terms" or lv.composite or not getattr(lv, "size", None):
        return False
    if "n_candidates" in aggs:
        return len(aggs["n_candidates"]["buckets"]) > FILTERED_CANDIDATES
    return len(aggs["s0"]["buckets"]) >= lv.size


def _keyset_count_agg(lv, field: str) -> Optional[dict]:
    """How many keys of a key-set filter the set holds: the kept keys, or the left-out
    keys to subtract from the split's cardinality. None past MAX_LEVEL_GROUPS keys."""
    if lv.include is not None:
        keys = sorted(lv.include - (lv.exclude or set()))
    elif lv.exclude:
        keys = sorted(lv.exclude)
    else:
        return None
    if not keys or len(keys) > MAX_LEVEL_GROUPS:
        return None
    return {"terms": {"field": field, "include": keys, "size": len(keys)}}


def _groups_count(lv, aggs: dict) -> Optional[int]:
    """A single split's number of groups after its key-set filter (None when unknown)."""
    n = (aggs.get("n_groups") or {}).get("value")
    present = (aggs.get("n_keyset") or {}).get("buckets")
    if lv.include is not None:
        if not (lv.include - (lv.exclude or set())):
            return 0
        return len(present) if present is not None else None
    if lv.exclude:
        return max(0, n - len(present)) if present is not None and n is not None else None
    return n


# ---------------------------------------------------------------------------
# Splits
# ---------------------------------------------------------------------------
_UNSUPPORTED_SPLITS = ("best_open_version", "mag_only")
_NONNEG_HINTS = ("count", "index", "h_index", "i10")


@dataclass
class Level:
    index: int
    split: GroupBy
    kind: str                                  # terms | filters | range | histogram
    agg: dict = field(default_factory=dict)    # the bucket agg body (no sub-aggs)
    labels: Dict[str, Tuple[str, str]] = field(default_factory=dict)  # bucket key -> (key, label)
    order_keys: List[str] = field(default_factory=list)               # filters: listed order
    column_id: Optional[str] = None
    is_float: bool = False
    group_entity: Optional[str] = None
    selector: Optional[Tuple[Dict[str, str], str]] = None
    include: Optional[set] = None
    exclude: Optional[set] = None
    post_keep: Optional[set] = None            # keys kept after a survivors lookup
    size: Optional[int] = None
    composite: bool = False                    # cursor paging (a single terms split)
    by_count: bool = False                     # filters: biggest first, empty ones dropped
    paged_floor: bool = False                  # a count floor sorted and paged by ES


def _label_bool(column_id: str, value: bool) -> str:
    from query_translation.oql_lang import _oql_field
    word = _oql_field(column_id)[0]
    return word if value else f"not {word}"


def _num(v) -> str:
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v)


def _bin_labels(column_id: str, edges: List, is_float: bool) -> List[str]:
    """Labels for `bins at (e1, ..., en)`: integers `0`, `1-9`, `10-99`, `100+`;
    decimals `under 0.5`, `0.5-1`, `1-2`, `2+` (lower edge inclusive)."""
    labels = []
    nonneg = any(h in column_id for h in _NONNEG_HINTS)
    for i in range(len(edges) + 1):
        lo = edges[i - 1] if i > 0 else None
        hi = edges[i] if i < len(edges) else None
        if hi is None:
            labels.append(f"{_num(lo)}+")
        elif lo is None:
            if not is_float and nonneg and float(hi).is_integer():
                top = int(hi) - 1
                labels.append("0" if top == 0 else (f"0-{top}" if top > 0 else f"under {_num(hi)}"))
            else:
                labels.append(f"under {_num(hi)}")
        elif not is_float and float(lo).is_integer() and float(hi).is_integer():
            top = int(hi) - 1
            labels.append(_num(lo) if top == int(lo) else f"{_num(lo)}-{top}")
        else:
            labels.append(f"{_num(lo)}-{_num(hi)}")
    return labels


def _is_integer_column(column_id: str) -> bool:
    from query_translation.oql_lang import is_integer_column
    return is_integer_column(column_id)


def _value_key(column_id: str, v) -> str:
    """The bucket key a listed value would have as a terms key."""
    if isinstance(v, str) and re.match(r"^[A-Za-z]\d+$", v):
        return ID_PREFIX + v[0].upper() + v[1:]
    return str(v)


def build_level(i: int, g: GroupBy, oqo: OQO, fields_dict, index_name: str) -> Level:
    import copy
    from core.utils import get_field
    from query_translation.oqo_to_es import _translate
    from query_translation.oql_lang import _group_entity
    from query_translation.oql_pipeline import _expr_text, _search_item_text

    group_entity = _group_entity(g, oqo.get_rows)
    if g.conditions is not None:
        lv = Level(i, g, "filters", group_entity=None)
        filters = {}
        for j, c in enumerate(g.conditions):
            k = f"c{j}"
            filters[k] = _translate(c, fields_dict).to_dict()
            text = _expr_text(c)
            lv.labels[k] = (text, text)
            lv.order_keys.append(k)
        lv.agg = {"filters": {"filters": filters}}
        return lv
    column_id = g.column_id
    if g.values is not None and column_id.endswith(".search"):
        lv = Level(i, g, "filters", column_id=column_id)
        filters = {}
        for j, v in enumerate(g.values):
            k = f"q{j}"
            filters[k] = _translate(v, fields_dict).to_dict()
            text = _search_item_text(v)
            lv.labels[k] = (text, text)
            lv.order_keys.append(k)
        lv.agg = {"filters": {"filters": filters}}
        return lv
    fld = get_field(fields_dict, column_id)
    if g.values is not None:
        lv = Level(i, g, "filters", column_id=column_id, group_entity=group_entity)
        values = list(g.values)
        if len(values) == 1 and isinstance(values[0], str) and values[0].startswith("col_"):
            from core.filter import resolve_collection_for_field
            _etype, ids = resolve_collection_for_field(fld, values[0])
            values = [i_.replace(ID_PREFIX, "") if isinstance(i_, str) else i_ for i_ in ids]
            if len(values) > 100:
                raise AnalyticsError(
                    "list_too_long",
                    f"The collection {g.values[0]} holds {len(values)} items; a split by "
                    f"listed values takes up to 100.",
                    "Split by the column itself and filter the works by the collection "
                    "instead: get works where ... is in the collection [name](col_x); then, "
                    "group those works by ...")
        filters = {}
        for j, v in enumerate(values):
            k = f"v{j}"
            filters[k] = _translate(LeafFilter(column_id, v), fields_dict).to_dict()
            lv.labels[k] = (_value_key(column_id, v), None)
            lv.order_keys.append(k)
        lv.agg = {"filters": {"filters": filters}}
        return lv
    if g.bins is not None:
        es_field = fld.es_field().replace("__", ".")
        is_float = not _is_integer_column(column_id)
        if "at" in g.bins:
            edges = g.bins["at"]
            ranges = []
            for j in range(len(edges) + 1):
                r = {"key": f"b{j}"}
                if j > 0:
                    r["from"] = edges[j - 1]
                if j < len(edges):
                    r["to"] = edges[j]
                ranges.append(r)
            labels = _bin_labels(column_id, edges, is_float)
            lv = Level(i, g, "range", column_id=column_id, is_float=is_float)
            lv.agg = {"range": {"field": es_field, "ranges": ranges, "keyed": False}}
            for j, lab in enumerate(labels):
                lv.labels[f"b{j}"] = (lab, lab)
                lv.order_keys.append(f"b{j}")
            return lv
        width = g.bins["of"]
        lv = Level(i, g, "histogram", column_id=column_id, is_float=is_float)
        lv.agg = {"histogram": {"field": es_field, "interval": width, "min_doc_count": 1}}
        return lv
    if "continent" in fld.param and g.bins is None:
        # a split by continent (#1494's cow path, oxjob #1555): continents come from
        # countries, so one filter per continent, biggest first, empty ones dropped
        from settings import CONTINENT_NAMES
        lv = Level(i, g, "filters", column_id=column_id, group_entity=group_entity, by_count=True)
        filters = {}
        for j, c in enumerate(CONTINENT_NAMES):
            k = f"v{j}"
            filters[k] = _translate(LeafFilter(column_id, c["id"]), fields_dict).to_dict()
            lv.labels[k] = (c["id"], c["display_name"])
            lv.order_keys.append(k)
        lv.agg = {"filters": {"filters": filters}}
        return lv
    # a plain column
    ftype = type(fld).__name__
    if fld.param in _UNSUPPORTED_SPLITS or "continent" in fld.param or "version" in fld.param:
        raise AnalyticsError(
            "split_not_available",
            f"Splitting by {fld.param} isn't available in calculations yet.",
            "Group by it without a calculation (today's group by), or split by another field.")
    if (ftype == "BooleanField" or fld.param in settings.EXTERNAL_ID_FIELDS
            or fld.param in settings.BOOLEAN_TEXT_FIELDS or "is_global_south" in fld.param):
        lv = Level(i, g, "filters", column_id=column_id)
        t = copy.copy(fld)
        t.value = "true"
        f_true = t.build_query()
        f = copy.copy(fld)
        f.value = "false"
        f_false = f.build_query()
        lv.agg = {"filters": {"filters": {"true": f_true.to_dict(), "false": f_false.to_dict()}}}
        lv.labels = {"true": ("true", _label_bool(column_id, True)),
                     "false": ("false", _label_bool(column_id, False))}
        lv.order_keys = ["true", "false"]
        return lv
    es_field = fld.alias if getattr(fld, "alias", None) else fld.es_sort_field()
    lv = Level(i, g, "terms", column_id=column_id, group_entity=group_entity)
    lv.agg = {"terms": {"field": es_field}}
    if "cited_by_percentile_year" in es_field:
        lv.agg["terms"]["format"] = "0.0"
    if type(fld).__name__ == "RangeField" and not _is_integer_column(column_id):
        raise AnalyticsError(
            "decimal_needs_bins",
            f"{column_id} is a decimal, so it can't split works by value.",
            "Split it into bins: group those works into ... bins at (0.5, 1, 2)")
    return lv


# ---------------------------------------------------------------------------
# Group filters: measures -> selector; own fields, co-author, collaborator -> key sets
# ---------------------------------------------------------------------------
def _nnf_group_filters(oqo: OQO) -> OQO:
    """Group filters in negation normal form: `that author is not in (A1, A2)` parses
    to a negated OR; the key-set rules read an AND of negated leaves."""
    from query_translation.oqo_canonicalizer import _canonicalize_tree
    return replace(oqo, group_by=[
        replace(g, where=_canonicalize_tree(g.where, sort_operands=False))
        if g.where is not None else g for g in oqo.group_by])


def _split_where(where) -> Tuple[List, List]:
    """(measure-only parts, key-set parts) of a group filter, ANDed. An OR that mixes
    calculations with the group's own fields can't run in one pass."""
    parts = where.filters if (isinstance(where, BranchFilter) and where.join == "and"
                              and not where.is_negated) else [where]
    measures, keysets = [], []
    for p in parts:
        if _is_measure_only(p):
            measures.append(p)
        elif not _has_measure(p):
            keysets.append(p)
        else:
            raise AnalyticsError(
                "group_filter_mix",
                "A group filter can't mix a calculation and a group's own field inside "
                "one `or`.",
                "Join them with `and`, or run two queries.")
    return measures, keysets


def _coauthor_keys(works_index, connection, column_ids: List[str], key_field: str,
                   match_field: str, deadline: Deadline, what: str) -> set:
    """Everyone who shares a work with any of `column_ids` (co-authors of an author,
    collaborators of an institution), as full ids, plus the ids themselves."""
    ids = [_value_key(match_field, v) for v in column_ids]
    body = {"size": 0, "query": {"bool": {"filter": [
        {"terms": {match_field: ids}}, {"term": {"is_xpac": False}}]}},
        "aggs": {"k": {"terms": {"field": key_field, "size": 65_000}}}}
    res = _search(works_index, connection, body, deadline, what)
    keys = {b["key"] for b in res["aggregations"]["k"]["buckets"]}
    if res["aggregations"]["k"].get("sum_other_doc_count"):
        raise AnalyticsError(
            "lookup_too_big",
            f"{', '.join(column_ids)} has more than 65,000 {what}s; the group filter can't "
            f"list them all.",
            "Filter by a calculation or a narrower relation instead.")
    return keys | set(ids)


# -- an author's record with years, and the smaller side (oxjob #1555, thing-first) --
# `at [UBC](I141945490) since 2022`: the authors index holds an author's institutions and
# their years in one flat object, so ES can only match the institution; the years are
# checked in each candidate's record (`_source.affiliations`). A precomputed
# institution-year keyword at the next authors rebuild would make it one terms query.
def _has_affiliation(node) -> bool:
    if isinstance(node, AffiliationFilter):
        return True
    return isinstance(node, BranchFilter) and any(_has_affiliation(c) for c in node.filters)


def _es_tree(node):
    """A group-filter part for ES: an affiliation with years as its year-less leaf (a
    superset of the candidates; the years are checked after)."""
    if isinstance(node, AffiliationFilter):
        if node.is_negated:
            raise AnalyticsError(
                "group_filter_not_available",
                "`not at` an institution in given years can't run yet.",
                "Say where they were instead, or drop the years: ever at ...")
        return LeafFilter(node.column_id, node.value)
    if isinstance(node, BranchFilter):
        if _has_affiliation(node) and not all(isinstance(c, (AffiliationFilter, BranchFilter))
                                              for c in node.filters):
            raise AnalyticsError(
                "group_filter_mix",
                "An `or` can't mix an affiliation in given years with other conditions.",
                "Join them with `and`.")
        return replace(node, filters=[_es_tree(c) for c in node.filters])
    return node


def _record_matches(node, src: dict) -> bool:
    """The years check on one author's record, for a part made of affiliations."""
    if isinstance(node, AffiliationFilter):
        return node.matches(src.get("affiliations") or []) != bool(node.is_negated)
    if isinstance(node, BranchFilter):
        r = (all if node.join == "and" else any)(_record_matches(c, src) for c in node.filters)
        return (not r) if node.is_negated else r
    return True


def _both_sides_too_big(lv: Level, n_own: Optional[int], n_keys: Optional[int]) -> AnalyticsError:
    """Loud, never a silent cap (oxjob #1555): neither side fits in the time."""
    ent = lv.group_entity
    keys = f"about {n_keys:,}" if n_keys is not None else "too many"
    return AnalyticsError(
        "query_too_slow",
        f"This query is too big to run in time: about {n_own or 0:,} {ent} match their own "
        f"conditions, and these works have {keys} {ent}. The engine checks up to "
        f"{LOOKUP_LIMIT:,} {ent} from their own records or {WORKS_SIDE_LIMIT:,} from the works.",
        f"Narrow the works (a shorter year range, a narrower search or topic) or the {ent} "
        f"(a smaller place, fewer years); a count filter also helps: who published more than "
        f"5 works where ...")


def _works_side_count(lv: Level, index, connection, base_query, deadline: Deadline) -> Optional[int]:
    """About how many distinct groups the works have (a cardinality probe)."""
    field = lv.agg["terms"]["field"]
    res = _search(index, connection, {"size": 0, "query": base_query, "aggs": {
        "n": {"cardinality": {"field": field, "precision_threshold": 40_000}}}},
        deadline, "counting the groups the works have")
    return res["aggregations"]["n"]["value"]


def record_ids(node, deadline: Optional[Deadline] = None, extra: Optional[dict] = None) -> set:
    """The authors whose own record matches an affiliation with years, for a list of
    authors (`get authors in [Brazil](BR) since 2022 where ...`, a set of them): the
    candidates are the authors with the place in their record who also match `extra`
    (the list's other conditions, an ES query); at most LOOKUP_LIMIT; loud past that."""
    lv = Level(0, GroupBy(column_id="authorships.author.id"), "terms", group_entity="authors")
    deadline = deadline or Deadline()
    positive = replace(node, is_negated=False)
    n = _count_entity_matches(lv, _es_tree(positive), deadline, extra)
    ids = _own_side_ids(lv, positive, n, deadline, extra)
    if ids is None:
        # a plain 400 (the list path's handler reads an AnalyticsError's code as a status)
        place = "that country" if node.column_id.endswith("country_code") else "that institution"
        raise APIQueryParamsError(
            f"About {n or 0:,} authors have {place} in their record and match the rest; a list "
            f"of authors by a place checks up to {RECORD_CHECK_LIMIT:,} records for the years. "
            "Fix: add the works they published (get authors in [Brazil](BR) who published works "
            "where ...), narrow the list (where h-index is above 50), name a smaller place, or "
            "drop the years: ever in [Brazil](BR) (anyone with it in their record).")
    return ids


def _own_side_ids(lv: Level, part, n: Optional[int], deadline: Deadline,
                  extra: Optional[dict] = None) -> Optional[set]:
    """The groups whose own record matches an affiliation-with-years part, listed from
    their own index when at most RECORD_CHECK_LIMIT (`n`, counted by the caller) match
    the place; None when more."""
    from query_translation.oqo_to_es import _translate
    from core.join_resolver import entity_index
    from elasticsearch_dsl.connections import get_connection
    if n is None or n > RECORD_CHECK_LIMIT:
        return None
    g_fields, g_index = entity_index(lv.group_entity)
    q = {"bool": {"filter": [_translate(_es_tree(part), g_fields).to_dict()]
                  + ([extra] if extra else [])}}
    keep, after, es = set(), None, get_connection()
    while True:
        body = {"size": 10_000, "_source": ["id", "affiliations"], "query": q,
                "sort": [{"id": "asc"}]}
        if after is not None:
            body["search_after"] = after
        try:
            res = es.search(index=g_index, body=body,
                            request_timeout=deadline.timeout("checking the groups' records"))
        except ConnectionTimeout:
            raise too_slow("checking the groups' records")
        hits = res["hits"]["hits"]
        keep |= {h["_source"]["id"] for h in hits if _record_matches(part, h["_source"])}
        if len(hits) < 10_000:
            return keep
        after = hits[-1]["sort"]


def resolve_keysets(lv: Level, parts: List, oqo: OQO, works_index: str, connection,
                    deadline: Deadline, has_measure_filter: bool,
                    base_query: Optional[dict] = None) -> List:
    """Turn the key-set parts of a group filter into lv.include / lv.exclude. Returns
    the parts that need the survivors lookup (own fields with too many matches)."""
    from query_translation.oqo_to_es import _translate
    from core.join_resolver import entity_index, resolve_query_ids
    from core.filter import resolve_collection

    include: Optional[set] = None
    exclude: set = set()
    deferred = []

    def add_include(keys):
        nonlocal include
        include = set(keys) if include is None else include & set(keys)

    for p in parts:
        leaves = [p] if isinstance(p, LeafFilter) else (
            p.filters if isinstance(p, BranchFilter) else [])
        simple = all(isinstance(x, LeafFilter) for x in leaves) and leaves and \
            len({(x.column_id, x.is_negated) for x in leaves}) == 1
        col = leaves[0].column_id if simple else None
        neg = leaves[0].is_negated if simple else None
        joins_ok = isinstance(p, LeafFilter) or (
            isinstance(p, BranchFilter) and p.join == ("and" if neg else "or")
            and not p.is_negated)
        if simple and joins_ok and col == "ids.openalex":
            keys = {_value_key(col, x.value) for x in leaves}
            exclude |= keys if neg else set()
            if not neg:
                add_include(keys)
            continue
        if simple and joins_ok and col == "collection" and len(leaves) == 1:
            _etype, ids = resolve_collection(str(leaves[0].value))
            keys = {_value_key("ids.openalex", i.replace(ID_PREFIX, "")) for i in ids}
            if neg:
                exclude |= keys
            else:
                add_include(keys)
            continue
        if simple and joins_ok and col in ("co_author", "collaborator"):
            if col == "co_author":
                keys = _coauthor_keys(works_index, connection, [x.value for x in leaves],
                                      "authorships.author.id", "authorships.author.id",
                                      deadline, "co-author")
            else:
                keys = _coauthor_keys(works_index, connection, [x.value for x in leaves],
                                      "authorships.institutions.lineage",
                                      "authorships.institutions.lineage",
                                      deadline, "collaborator")
            if neg:
                exclude |= keys
            else:
                add_include(keys)
            continue
        # The group's own fields. With a calculation in the filter (a count filter),
        # look up only the groups that pass it, after the main request (#1512: 2
        # calls, 2.9 s for kelp authors); without one, list the matching groups in
        # their own index first and pass them as `include`.
        if has_measure_filter:
            # a count floor first (`who published at least 5 works where ...`): the groups
            # that pass it, checked in their own records side by side before the main
            # request (oxjob #1555: KU's 18,902 authors with 5+ KU works ran past the
            # 20,000 candidates the after-the-fact check takes); else after the request
            floor = _min_doc_count(lv.split.where)
            keys = (_count_floor_keys(lv, works_index, connection, base_query, deadline, floor)
                    if floor > 1 and base_query is not None and lv.kind == "terms" else None)
            if keys is None:
                deferred.append(p)
                continue
            from query_translation import walk_exec as WX
            add_include(set(WX.narrow(WX.Ctx(connection, deadline), lv.group_entity,
                                      sorted(keys), p)))
            continue
        # The smaller side (oxjob #1555): list the groups whose own fields match (UBC's
        # authors), or the groups the works have, checked in their own records (the
        # kelp works' authors), whichever is fewer; loud when both are too many.
        n_keys = (_works_side_count(lv, works_index, connection, base_query, deadline)
                  if base_query is not None and lv.kind == "terms" else None)
        n_own = _count_entity_matches(lv, _es_tree(p), deadline)
        ids = None
        if n_keys is None or n_own is None or n_own <= n_keys:
            if _has_affiliation(p):
                ids = _own_side_ids(lv, p, n_own, deadline)
            else:
                g_fields, _g_index = entity_index(lv.group_entity)
                q = _translate(p, g_fields)
                extra = [Q("range", works_count={"gt": 0})] if lv.group_entity == "authors" else []
                q_all = Q("bool", filter=[q] + extra) if extra else q
                ids = resolve_query_ids(lv.group_entity, q_all,
                                        json.dumps(p.to_dict(), sort_keys=True), LOOKUP_LIMIT,
                                        request_timeout=deadline.timeout("looking up the groups' own fields"))
        if ids is None and n_keys is not None and n_keys <= WORKS_SIDE_LIMIT:
            # list the works' groups and check their records side by side, as a walk does
            from query_translation import walk_exec as WX
            ctx = WX.Ctx(connection, deadline)
            keys = WX.list_keys(ctx, base_query, lv.agg["terms"]["field"], n_keys,
                                "listing the groups the works have")
            ids = set(WX.narrow(ctx, lv.group_entity, keys, p))
        if ids is None:
            if base_query is None or lv.kind != "terms":
                deferred.append(p)
                continue
            raise _both_sides_too_big(lv, n_own, n_keys)
        add_include(ids)
    lv.include = include
    lv.exclude = exclude or None
    return deferred


def survivors_lookup(lv: Level, parts: List, keys: List[str], deadline: Deadline) -> set:
    """Of `keys` (the groups that passed the rest of the filter), the ones whose own
    fields match `parts`: one lookup, ids chunked."""
    from query_translation.oqo_to_es import _translate
    from core.join_resolver import entity_index
    from elasticsearch_dsl.connections import get_connection
    g_fields, g_index = entity_index(lv.group_entity)
    filters = [_translate(_es_tree(p), g_fields).to_dict() for p in parts]
    years = [p for p in parts if _has_affiliation(p)]   # checked in each record (#1555)
    keep = set()
    es = get_connection()
    # a plain id-filtered search, 10,000 ids a call (a composite over the 100M-row
    # authors index took 3 s for 495 ids; this takes about 0.1 s)
    for start in range(0, len(keys), 10_000):
        chunk = keys[start:start + 10_000]
        body = {"size": len(chunk), "_source": ["id", "affiliations"] if years else ["id"],
                "query": {"bool": {"filter": [{"terms": {"id": chunk}}] + filters}}}
        try:
            res = es.search(index=g_index, body=body,
                            request_timeout=deadline.timeout("checking the groups' own fields"))
        except ConnectionTimeout:
            raise too_slow("checking the groups' own fields")
        keep |= {h["_source"]["id"] for h in res["hits"]["hits"]
                 if all(_record_matches(p, h["_source"]) for p in years)}
    return keep


# ---------------------------------------------------------------------------
# Running
# ---------------------------------------------------------------------------
def _search(index, connection, body, deadline: Deadline, what: str, **params) -> dict:
    from elasticsearch_dsl.connections import get_connection
    es = get_connection(connection)
    try:
        return es.search(index=index, body=body, request_timeout=deadline.timeout(what),
                         **params)
    except ConnectionTimeout:
        raise too_slow(what)
    except TransportError as e:
        text = str(getattr(e, "info", "") or e)
        if "too_many_buckets" in text:
            raise AnalyticsError(
                "too_many_groups",
                f"This query would return more than {MAX_RESPONSE_BUCKETS:,} groups in one "
                f"answer.",
                "Narrow the starting set, or drop a split: one split pages through any "
                "number of groups.")
        raise


def _cardinalities(levels: List[Level], index, connection, base_query, deadline) -> Dict[int, int]:
    """The group guard's estimate: distinct keys of each terms split in the set."""
    return _probe(levels, index, connection, base_query, deadline)[1]


def _probe(levels: List[Level], index, connection, base_query, deadline) -> Tuple[int, Dict[int, int]]:
    """(works in the set, distinct keys of each terms split): one cheap request."""
    terms = [lv for lv in levels if lv.kind == "terms"]
    aggs = {f"card{lv.index}": {"cardinality": {"field": lv.agg["terms"]["field"],
                                                "precision_threshold": 3000}}
            for lv in terms}
    body = {"size": 0, "track_total_hits": True, "query": base_query}
    if aggs:
        body["aggs"] = aggs
    res = _search(index, connection, body, deadline, "counting the groups")
    return (res["hits"]["total"]["value"],
            {lv.index: res["aggregations"][f"card{lv.index}"]["value"] for lv in terms})


# Every combination of the terms splits' values in one document, as one key (multi-
# valued fields give their cross product): its distinct count is the group guard's
# estimate of a nested split's groups (#1512: multiplying per-split counts overestimated
# MIT's year x type x OA status 5.9-fold; this gives 4,142 against 4,159 real).
_COMBO_SCRIPT = """
List out = new ArrayList(); out.add('');
for (String f : params.fields) {
  List nxt = new ArrayList();
  def vals = doc[f];
  if (vals.size() == 0) { for (def p : out) { nxt.add(p + '|_'); } }
  else { for (def p : out) { for (def v : vals) { nxt.add(p + '|' + v); } } }
  out = nxt;
}
return out;
"""


def _combined_groups(levels: List[Level], index, connection, base_query, deadline) -> int:
    """Estimated groups of a nested split: the distinct combined keys of its terms
    splits, times the group count of its other splits (listed values, bins)."""
    fields = [lv.agg["terms"]["field"] for lv in levels if lv.kind == "terms"]
    other = 1
    for lv in levels:
        if lv.kind == "filters":
            other *= max(len(lv.order_keys), 1)
        elif lv.kind == "range":
            other *= max(len(lv.order_keys), 1)
        elif lv.kind == "histogram":
            other *= 100
    body = {"size": 0, "query": base_query, "aggs": {"combo": {"cardinality": {
        "script": {"source": _COMBO_SCRIPT, "params": {"fields": fields}},
        "precision_threshold": 1000}}}}
    res = _search(index, connection, body, deadline, "counting the combined groups")
    return int(res["aggregations"]["combo"]["value"]) * other


def guard_nested(levels: List[Level], cards: Dict[int, int], index, connection,
                 base_query, deadline) -> Optional[int]:
    """The group guard on nested splits: refuse when the splits' combined groups pass
    what one answer can hold (ES search.max_buckets). Multiplies the per-split counts
    first; only when that product is over the line does it count the combined keys."""
    if len(levels) < 2:
        return None
    if any(lv.split.where is not None and lv.selector is not None
           and _min_doc_count(lv.split.where) > 1 for lv in levels):
        return None   # count-filtered: checked on the answer instead (truncated_levels)
    product = 1
    for lv in levels:
        if lv.kind == "terms":
            product *= max(cards.get(lv.index) or 1, 1)
        elif lv.kind in ("filters", "range"):
            product *= max(len(lv.order_keys), 1)
        else:
            product *= 100
    if product <= MAX_RESPONSE_BUCKETS:
        return product
    if not any(lv.kind == "terms" for lv in levels):
        n = product
    else:
        n = _combined_groups(levels, index, connection, base_query, deadline)
    if n > MAX_RESPONSE_BUCKETS:
        names = " x ".join(_split_noun(lv) for lv in levels)
        raise AnalyticsError(
            "too_many_groups",
            f"Splitting by {names} gives about {n:,} groups together; one answer holds "
            f"up to {MAX_RESPONSE_BUCKETS:,}.",
            "Narrow the starting set (a shorter year range), split by something coarser "
            "(field instead of topic), or drop a split: one split pages through any "
            "number of groups.")
    return n


def _count_floor_keys(lv: Level, index, connection, base_query, deadline: Deadline,
                      floor: int) -> Optional[List[str]]:
    """The keys of a split with at least `floor` works (one terms request, no
    sub-aggregations); None when more than WORKS_SIDE_LIMIT, or more than one request
    can list (65,000)."""
    limit = min(WORKS_SIDE_LIMIT, 65_000)
    terms = {"field": lv.agg["terms"]["field"], "size": limit + 1, "min_doc_count": floor,
             "shard_size": limit + 1}
    res = _search(index, connection, {"size": 0, "query": base_query, "aggs": {"k": {"terms": terms}}},
                  deadline, "finding the groups that pass the count")
    keys = [str(b["key"]) for b in res["aggregations"]["k"]["buckets"]]
    return keys if len(keys) <= limit else None


def _count_survivors(lv: Level, index, connection, base_query, deadline) -> set:
    """The keys of a split that pass its count filter, from a terms request with no
    sub-aggregations. Refuses when more than MAX_LEVEL_GROUPS pass."""
    terms = {"field": lv.agg["terms"]["field"], "size": MAX_LEVEL_GROUPS + 1,
             "min_doc_count": _min_doc_count(lv.split.where)}
    if lv.exclude:
        terms["exclude"] = sorted(lv.exclude)
    body = {"size": 0, "query": base_query, "aggs": {"k": {"terms": terms}}}
    res = _search(index, connection, body, deadline, "finding the groups that pass the count")
    keys = {b["key"] for b in res["aggregations"]["k"]["buckets"]}
    if len(keys) > MAX_LEVEL_GROUPS:
        raise AnalyticsError(
            "too_many_groups",
            f"More than {MAX_LEVEL_GROUPS:,} {_split_noun(lv)} groups pass the count filter; "
            f"a nested split takes up to {MAX_LEVEL_GROUPS:,} per split.",
            "Raise the count threshold, narrow the starting set, or make it the only split.")
    return keys


def _cards_product(levels: List[Level], cards: Dict[int, int]) -> int:
    p = 1
    for lv in levels:
        if lv.kind == "terms":
            p *= max(cards.get(lv.index) or 1, 1)
        elif lv.kind in ("filters", "range"):
            p *= max(len(lv.order_keys), 1)
        else:
            p *= 100
    return p


def estimate_main_seconds(n_works: int, groups: int, base_search: bool = False) -> float:
    """The main request's time: about (works / 1e8) x (1 + groups / 5,000) seconds,
    fitted 2026-10-03 (2020+ topic x year, 104M works, 32K groups: 8 s; MIT year x
    type x OA, 0.4M works, 4K groups: 0.4 s; field x year, 256M works: 0.5-1.3 s). A
    split can't make more groups than its works times a few values each, so the
    group count is capped at 5 per work."""
    g = min(groups or 1, max(n_works, 1) * 5)
    t = (n_works / EST_WORKS_PER_S) * (1 + g / EST_GROUPS_SCALE)
    return max(t, EST_CALL_SEARCH_SET_S if base_search else 0.1)


def check_truncated(levels: List[Level], aggs: dict):
    """A count-filtered nested split takes up to MAX_LEVEL_GROUPS groups per parent;
    if one came back full, more may have passed: refuse rather than cut silently."""
    def walk(level_i, agg):
        lv = levels[level_i]
        buckets = agg.get("buckets")
        if lv.kind == "terms" and isinstance(buckets, list) and lv.size \
                and len(buckets) >= lv.size:
            raise AnalyticsError(
                "too_many_groups",
                f"More than {lv.size:,} {_split_noun(lv)} groups passed the filter in one "
                f"group; a nested split takes up to {MAX_LEVEL_GROUPS:,} per split.",
                "Raise the count threshold, narrow the starting set, or make it the only "
                "split.")
        items = buckets.values() if isinstance(buckets, dict) else (buckets or [])
        for b in items:
            nxt = f"s{level_i + 1}"
            if level_i + 1 < len(levels) and nxt in b:
                walk(level_i + 1, b[nxt])
    if len(levels) > 1 and "s0" in aggs:
        walk(0, aggs["s0"])


def _split_noun(lv: Level) -> str:
    from query_translation.oql_lang import _split_label
    return _split_label(lv.split)


def plan_levels(levels: List[Level], cards: Dict[int, int], nested: bool, per_page: int,
                page: int, sort_measure: Optional[str]):
    """Sizes and order for the terms splits; refuses what the group guard can't take."""
    for lv in levels:
        if lv.kind != "terms" or lv.composite:
            continue
        card = cards.get(lv.index)
        terms = lv.agg["terms"]
        counted = (lv.split.where is not None and lv.selector is not None
                   and _min_doc_count(lv.split.where) > 1)
        if nested and counted:
            # a count filter keeps far fewer groups than the split has; take up to the
            # cap and say so loudly if more than that pass (checked after the request)
            size = MAX_LEVEL_GROUPS
        elif nested:
            if card is not None and card > MAX_LEVEL_GROUPS:
                raise AnalyticsError(
                    "too_many_groups",
                    f"Splitting by {_split_noun(lv)} gives about {card:,} groups here; a "
                    f"nested split takes up to {MAX_LEVEL_GROUPS:,} groups per split.",
                    "Narrow the starting set, or make it the only split (one split pages "
                    "through any number of groups).")
            size = min(int((card or MAX_LEVEL_GROUPS) * 1.1) + 10, MAX_LEVEL_GROUPS)
        elif (lv.selector is not None and lv.post_keep is None and sort_measure
              and sort_measure != {"_count": "desc"} and _count_floor_only(lv.split.where)):
            # a count floor is min_doc_count, applied before the split is sized, so ES
            # sorts and pages it exactly (one extra group says whether more follow)
            if page * per_page > MAX_PAGE_DEPTH:
                raise AnalyticsError(
                    "page_too_deep",
                    f"Page {page} of {per_page} groups goes past the first "
                    f"{MAX_PAGE_DEPTH:,} groups.",
                    "Sort the groups so the ones you want come first.")
            size = page * per_page + 1
            lv.paged_floor = True
        elif lv.selector is not None or lv.post_keep is not None:
            size = FILTERED_CANDIDATES
        else:
            size = page * per_page
            if size > MAX_PAGE_DEPTH:
                raise AnalyticsError(
                    "page_too_deep",
                    f"Page {page} of {per_page} groups goes past the first "
                    f"{MAX_PAGE_DEPTH:,} groups.",
                    "Sort the groups so the ones you want come first, or page through "
                    "every group with cursor=* (in key order).")
        terms["size"] = size
        terms["shard_size"] = max(size * 2, 3000)
        lv.size = size
        order = [{"_count": "desc"}, {"_key": "asc"}]
        if sort_measure and not nested and (lv.selector is None or lv.paged_floor):
            order = ((sort_measure if isinstance(sort_measure, list) else [sort_measure])
                     + [{"_key": "asc"}])
        terms["order"] = order
        if lv.include is not None:
            inc = sorted(lv.include - (lv.exclude or set()))
            terms["include"] = inc if inc else ["__none__"]
        elif lv.exclude:
            terms["exclude"] = sorted(lv.exclude)
        if lv.selector is not None and lv.split.where is not None:
            terms["min_doc_count"] = _min_doc_count(lv.split.where)


def build_body(levels: List[Level], base_query, measure_aggs: Dict[str, dict]) -> dict:
    """The one request: nested split aggs with measures at every level, plus the same
    measures at the root (the summary's whole-set row) and each inner split alone."""
    def level_aggs(lv: Level, inner: Dict[str, dict]) -> dict:
        sub = dict(measure_aggs)
        sub.update(inner)
        if lv.selector is not None:
            paths, script = lv.selector
            sub["having"] = {"bucket_selector": {"buckets_path": paths, "script": script}}
        body = dict(lv.agg)
        if sub:
            body["aggs"] = sub
        return body

    inner: Dict[str, dict] = {}
    for lv in reversed(levels):
        inner = {f"s{lv.index}": level_aggs(lv, inner)}
    aggs = dict(measure_aggs)
    aggs.update(inner)
    # The summary (#1550): each inner split on its own over the whole set (the world
    # by SDG), computed from the works; the outer split on its own is s0 itself.
    for lv in levels[1:]:
        aggs[f"m{lv.index}"] = level_aggs(lv, {})
    return {"size": 0, "track_total_hits": True, "query": base_query, "aggs": aggs}


_ANNOTATED_VALUE = re.compile(r"([^\s(]+) \[([^\]]+)\]")
MAX_NAMED_CONDITION_IDS = 20


def _name_conditions(levels: List[Level], entity: str) -> None:
    """Condition groups read by name, `institution is (KU Leuven)`; the key keeps the
    ids. One display-name lookup per id."""
    from query_translation.oql_pipeline import _expr_text
    from query_translation.oql_renderer import make_engine_resolver
    from query_translation.x_query import safe_get_display_name
    for lv in levels:
        if lv.split.conditions is None:
            continue
        # shortcut: one lookup per id; past 20 ids the labels keep the ids
        ids = set()
        for c in lv.split.conditions:
            ids.update(re.findall(r"\b[A-Z]\d{4,}\b", _expr_text(c)))
        if len(ids) > MAX_NAMED_CONDITION_IDS:
            continue
        resolver = make_engine_resolver(safe_get_display_name, entity=entity)
        for k, c in zip(lv.order_keys, lv.split.conditions):
            try:
                named = _ANNOTATED_VALUE.sub(
                    lambda m: m.group(1) if m.group(2) == "no entity found" else m.group(2),
                    _expr_text(c, resolver))
            except Exception:
                continue
            lv.labels[k] = (lv.labels[k][0], named)


def _display_names(lv: Level, raw_keys: List, connection) -> Dict:
    """bucket key -> display name, the legacy group-by's way."""
    from elasticsearch_dsl import AttrDict
    from core.group_by.display_names import (
        get_display_name_mapping, get_key_display_name, requires_display_name_conversion)
    col = lv.column_id
    keys = [k for k in raw_keys if k not in (None, "unknown")]
    if not keys:
        return {}
    if requires_display_name_conversion(col) and _plain_id_column(col):
        fast = _id_names(keys, connection)
        if fast is not None:
            return fast
    if requires_display_name_conversion(col):
        names = {}
        for start in range(0, len(keys), 500):
            chunk = keys[start:start + 500]
            try:
                got = get_display_name_mapping(chunk, col, connection) or {}
            except Exception:
                got = {}
            names.update(got)
        return names
    out = {}
    for k in keys:
        try:
            out[k] = get_key_display_name(AttrDict({"key": k}), col)
        except Exception:
            out[k] = str(k)
    return out


_SPECIAL_NAME_COLUMNS = ("host_organization", "host_organization_lineage", "domain.id",
                         "subfield.id", "subfields.id", "field.id", "fields.id",
                         "keywords.id", "sustainable_development_goals.id",
                         "study_designs.id", "license", "license_id")


def _plain_id_column(col: str) -> bool:
    """Columns the legacy namer looks up by OpenAlex id (not a special table)."""
    return not any(col.endswith(s) for s in _SPECIAL_NAME_COLUMNS)


def _id_names(keys: List, connection) -> Optional[Dict]:
    """Display names for OpenAlex-id keys with one `terms` query per index (the legacy
    namer's 200-clause `should` took 1.2 s for 200 authors). None when a key isn't an
    OpenAlex id this can route (the caller falls back to the legacy namer)."""
    from core.utils import get_index_name_by_id
    from elasticsearch_dsl.connections import get_connection
    by_index: Dict[str, List] = {}
    for k in keys:
        try:
            idx = get_index_name_by_id(str(k), connection)
        except Exception:
            return None
        if idx is None:
            return None
        by_index.setdefault(idx, []).append(k)
    es = get_connection(connection)
    names: Dict = {}
    for idx, ks in by_index.items():
        for start in range(0, len(ks), 1000):
            chunk = ks[start:start + 1000]
            res = es.search(index=idx, body={
                "size": len(chunk), "_source": ["id", "display_name"],
                "query": {"terms": {"id": chunk}}}, request_timeout=3)
            for h in res["hits"]["hits"]:
                names[h["_source"]["id"]] = h["_source"].get("display_name")
    return names


def _bucket_rows(lv: Level, agg: dict) -> List[Tuple[str, dict]]:
    """(bucket key, bucket) in display order for one level's aggregation result."""
    buckets = agg["buckets"]
    if isinstance(buckets, dict):          # filters
        rows = [(k, buckets[k]) for k in lv.order_keys]
        if lv.by_count:
            rows = sorted([r for r in rows if r[1]["doc_count"]], key=lambda r: -r[1]["doc_count"])
        return rows
    if lv.composite:
        return [(b["key"]["k"], b) for b in buckets]
    if lv.kind == "range":
        return [(b["key"], b) for b in buckets]
    if lv.kind == "histogram":
        return [(b["key"], b) for b in buckets]
    return [(b.get("key_as_string", b["key"]) if isinstance(b["key"], (int, float)) and lv.column_id and
             "percentile" in lv.column_id else b["key"], b) for b in buckets]


def format_levels(levels: List[Level], measures: List[Measure], agg_root: dict,
                  total_count: int, index_name: str) -> Tuple[List[dict], Dict[int, List[dict]]]:
    """Rows for every level, unnamed (`name_rows` names the ones that are returned),
    and each inner split's groups on their own over the whole set (for the summary)."""
    from core.group_by.results import format_key

    def rows(level_i: int, agg: dict, parent_count: int) -> List[dict]:
        lv = levels[level_i]
        out = []
        for k, b in _bucket_rows(lv, agg):
            count = b["doc_count"]
            if lv.kind == "terms":
                if lv.post_keep is not None and k not in lv.post_keep:
                    continue
                if lv.composite and ((lv.include is not None and k not in lv.include)
                                     or (lv.exclude and k in lv.exclude)):
                    continue   # composite has no include/exclude
                key = format_key(k, lv.column_id, index_name) if isinstance(k, str) else str(k)
                if isinstance(k, (int, float)) and "openalex.org" not in str(k) and lv.column_id \
                        and lv.column_id.endswith(".id") and lv.group_entity:
                    key = f"{ID_PREFIX}{lv.group_entity}/{k}"
                label, raw = None, k
            elif lv.kind == "filters":
                key, label = lv.labels[k]
                raw = None
                if label is None:
                    raw = key
                    key = format_key(raw, lv.column_id, index_name)
                if lv.post_keep is not None and key not in lv.post_keep:
                    continue
                if lv.include is not None and key not in lv.include:
                    continue
                if lv.exclude and key in lv.exclude:
                    continue
            elif lv.kind == "range":
                key, label = lv.labels[k]
            else:  # histogram
                lo = k
                w = lv.split.bins["of"]
                if lv.is_float:
                    label = f"{_num(round(lo, 10))}-{_num(round(lo + w, 10))}"
                else:
                    hi = int(lo + w - 1)
                    label = _num(lo) if hi == int(lo) else f"{_num(lo)}-{hi}"
                key = label
            row = {"key": key, "key_display_name": label, "count": count}
            if lv.kind in ("terms", "filters") and raw is not None:
                row["_raw"] = (level_i, raw)
            for m in measures:
                if m.measure != "count":
                    row[m.key] = _measure_value(m, b, count, parent_count)
            nxt = f"s{level_i + 1}"
            if level_i + 1 < len(levels) and nxt in b:
                row["groups"] = rows(level_i + 1, b[nxt], count)
            out.append(row)
        return out

    out = rows(0, agg_root["s0"], total_count)
    margins = {lv.index: rows(lv.index, agg_root[f"m{lv.index}"], total_count)
               for lv in levels[1:] if f"m{lv.index}" in agg_root}
    return out, margins


def name_rows(levels: List[Level], rows: List[dict], connection) -> List[dict]:
    """Display names for the rows being returned (the page, not every candidate
    group): one lookup per level. Drops merged or deleted authors, as the legacy
    group-by does."""
    raw_by_level: Dict[int, set] = {}

    def collect(rs):
        for r in rs:
            if "_raw" in r:
                raw_by_level.setdefault(r["_raw"][0], set()).add(r["_raw"][1])
            collect(r.get("groups") or [])

    collect(rows)
    names = {i: _display_names(levels[i], sorted(ks, key=str), connection)
             for i, ks in raw_by_level.items()}

    def fill(rs):
        out = []
        for r in rs:
            if "_raw" in r:
                i, k = r.pop("_raw")
                name = names.get(i, {}).get(k)
                if levels[i].column_id == "authorships.author.id" and not name:
                    continue
                r["key_display_name"] = str(k) if name is None else str(name)
            if r.get("groups"):
                r["groups"] = fill(r["groups"])
            out.append(r)
        return out

    return fill(rows)


def fill_own_values(levels: List[Level], rows: List[dict], measures: List[Measure],
                    deadline: Deadline, start_level: int = 0):
    """`value` measures (a split's own field: each author's h-index): one lookup per
    level, by the groups' ids, in the group entity's own index."""
    from core.join_resolver import entity_index
    from core.utils import get_field
    from elasticsearch_dsl.connections import get_connection
    wanted = [m for m in measures if m.measure == "value"]
    if not wanted:
        return
    by_level: Dict[int, List[dict]] = {}

    def walk(rs, level_i):
        by_level.setdefault(level_i, []).extend(rs)
        for r in rs:
            if r.get("groups") and level_i + 1 < len(levels):
                walk(r["groups"], level_i + 1)
    walk(rows, start_level)
    for lv in levels:
        level_rows = by_level.get(lv.index, [])
        if not level_rows or not lv.group_entity:
            continue
        try:
            g_fields, g_index = entity_index(lv.group_entity)
        except ValueError:
            continue
        # the record's own path: the column id (`summary_stats.h_index`), which is how
        # the document stores it (the filter field can be a flattened copy,
        # `summary_stats__h_index`)
        paths = {m.key: m.column_id for m in wanted if m.column_id in g_fields}
        if not paths:
            continue
        # an ID's name sits beside it (`last_known_institutions.display_name`)
        source = ["id"] + list(paths.values()) + [
            p[: -len(".id")] + ".display_name" for p in paths.values() if p.endswith(".id")]
        keys = [r["key"] for r in level_rows if isinstance(r.get("key"), str)
                and r["key"].startswith(ID_PREFIX)]
        found: Dict[str, dict] = {}
        for start in range(0, len(keys), 1000):
            chunk = keys[start:start + 1000]
            res = get_connection().search(
                index=g_index, body={"size": len(chunk), "_source": source,
                                     "query": {"terms": {"id": chunk}}},
                request_timeout=deadline.timeout("reading the groups' own fields"))
            for h in res["hits"]["hits"]:
                found[h["_source"]["id"]] = h["_source"]
        for r in level_rows:
            src = found.get(r.get("key"))
            for key, path in paths.items():
                r[key] = own_value(src, path, lv.group_entity)


def own_value(src: Optional[dict], path: str, entity: str):
    """A group's own field as one cell (oxjob #1555): a number or a yes/no as stored
    (an author's h-index); an ID as its name (`last known institution` -> "University
    of Washington"), a code as its name (`country` -> "United States"); several joined
    with "; " (an author with two last known institutions)."""
    parts = path.split(".")
    is_id = len(parts) > 1 and parts[-1] == "id"
    vals = [src]
    for part in (parts[:-1] if is_id else parts):
        nxt = []
        for v in vals:
            v = v.get(part) if isinstance(v, dict) else None
            nxt.extend(v if isinstance(v, list) else ([] if v is None else [v]))
        vals = nxt
    if is_id:
        vals = [v.get("display_name") or v.get("id") for v in vals if isinstance(v, dict)
                and (v.get("display_name") or v.get("id"))]
    elif vals and all(isinstance(v, str) for v in vals):
        vals = [_code_name(v, path, entity) for v in vals]
    if not vals:
        return None
    if len(vals) == 1:
        return vals[0]
    return "; ".join(str(v) for v in dict.fromkeys(vals))


def _code_name(code: str, column_id: str, entity: str) -> str:
    """A closed vocabulary's code as its name (`US` -> "United States"); else the code."""
    try:
        from query_translation.oql_lang import entity_type_for_column
        from query_translation.oql_renderer import _config_table
        from query_translation.validator import CLOSED_VOCAB_NAMESPACE
        ns = CLOSED_VOCAB_NAMESPACE.get(entity_type_for_column(column_id, entity) or "")
        name = (_config_table(ns) or {}).get(code.lower()) if ns else None
    except Exception:  # noqa: BLE001 (no vocabulary table: the code itself)
        name = None
    return name or code


def _sort_rows(rows: List[dict], sort: Optional[Tuple[str, str]]):
    if not sort:
        return rows
    key, direction = sort
    present = [r for r in rows if r.get(key) is not None]
    missing = [r for r in rows if r.get(key) is None]
    present.sort(key=lambda r: (r[key], str(r["key"])), reverse=(direction == "desc"))
    return present + missing


def run(oqo: OQO, *, index_name: str, connection, fields_dict, base_query: dict,
        per_page: Optional[int] = None, page: Optional[int] = None,
        sort: Optional[Tuple[str, str]] = None, deadline: Optional[Deadline] = None) -> dict:
    """Execute an analytics OQO. Returns the response body (without x_query)."""
    deadline = deadline or Deadline()
    per_page = per_page or DEFAULT_PER_PAGE
    page = page or 1
    measures = list(oqo.calculate) or [Measure("count")]
    oqo = _nnf_group_filters(oqo)
    levels = [build_level(i, g, oqo, fields_dict, index_name) for i, g in enumerate(oqo.group_by)]
    nested = len(levels) > 1

    # group filters: measures -> selector, own fields -> key sets
    agg_measures = list(measures)
    deferred: Dict[int, List] = {}
    for lv in levels:
        if lv.split.where is None:
            continue
        m_parts, k_parts = _split_where(lv.split.where)
        if m_parts:
            tree = m_parts[0] if len(m_parts) == 1 else BranchFilter("and", m_parts)
            lv.selector = _selector_script(tree)
            for m in _measures_in(tree):
                if m not in agg_measures:
                    agg_measures.append(m)
        if k_parts:
            if lv.group_entity is None:
                raise AnalyticsError(
                    "group_filter_not_available",
                    "These groups have no fields of their own to filter on.",
                    f"Filter by a calculation, e.g. {count_fix(lv)}.")
            rest = resolve_keysets(lv, k_parts, oqo, index_name, connection, deadline,
                                   bool(m_parts), base_query=base_query)
            if rest:
                if lv.kind != "terms" and lv.kind != "filters":
                    raise AnalyticsError("group_filter_not_available",
                                         "These groups can't be looked up.", "")
                if not m_parts and lv.kind == "terms":
                    raise AnalyticsError(
                        "query_too_slow",
                        f"The filter on the {lv.group_entity}' own fields matches more than "
                        f"{LOOKUP_LIMIT:,} {lv.group_entity}, and without a count filter "
                        f"every group in the set would have to be looked up, which takes "
                        f"longer than this query's time limit.",
                        f"Add a count filter so only the busiest groups are looked up "
                        f"({count_fix(lv, 5)}), or narrow the starting set.")
                deferred[lv.index] = rest
                lv.post_keep = set()   # filled after the main request

    m_aggs = _measure_aggs(agg_measures, fields_dict)
    n_works, cards = (_probe(levels, index_name, connection, base_query, deadline)
                      if (nested and any(lv.kind == "terms" for lv in levels)) else (None, {}))

    sort_measure = None
    if sort and not nested:
        key, direction = sort
        m = next((x for x in measures if x.key == key), None)
        if key == "count":
            sort_measure = {"_count": direction}
        elif m is not None and m.measure in ("mean", "sum", "min", "max", "median"):
            # groups with no value (a mean of nothing) sort last either way: first by
            # "has a value", then by the measure (ES put null means first on desc)
            path = f"m_{m.key}[50.0]" if m.measure == "median" else f"m_{m.key}"
            es_field = _es_number_field(fields_dict, m.column_id)
            m_aggs[f"h_{m.key}"] = {"max": {"script": {
                "source": f"doc['{es_field}'].size() > 0 ? 1 : 0"}}}
            sort_measure = [{f"h_{m.key}": "desc"}, {path: direction}]
        elif key == "key":
            sort_measure = {"_key": direction}
        # percent and percent_of_those sort after the fact (one page of groups)
    cursor = oqo.cursor
    if cursor is not None:
        # one split pages through any number of groups, in key order (composite)
        if not levels or nested or levels[0].kind != "terms":
            raise AnalyticsError(
                "cursor_not_available",
                "Cursor paging works on a single split by a column.",
                "Nested splits, listed values, bins and conditions return all their "
                "groups at once; drop the cursor.")
        if sort:
            raise AnalyticsError(
                "cursor_not_available",
                "Cursor paging goes through the groups in key order, so it can't sort.",
                "Drop the sort, or use page= to read the first groups in sorted order.")
        lv = levels[0]
        comp = {"size": per_page,
                "sources": [{"k": {"terms": {"field": lv.agg["terms"]["field"]}}}]}
        if cursor != "*":
            comp["after"] = {"k": _decode_cursor(cursor)}
        lv.agg = {"composite": comp}
        lv.composite = True
    if nested and levels[0].kind == "terms" and levels[0].selector is not None \
            and levels[0].split.where is not None and _min_doc_count(levels[0].split.where) > 1:
        # A count-filtered outer split: list the groups that pass the count first (no
        # sub-aggregations, cheap), then run the nested request on those keys only;
        # 72 shards each sending 20,000 groups with their inner splits ran past 15 s.
        survivors = _count_survivors(levels[0], index_name, connection, base_query, deadline)
        lv0 = levels[0]
        lv0.include = survivors if lv0.include is None else (lv0.include & survivors)
        cards[0] = len(lv0.include)
    plan_levels(levels, cards, nested, per_page, page, sort_measure)
    if nested:
        groups = guard_nested(levels, cards, index_name, connection, base_query, deadline)
        if n_works is not None:
            est = estimate_main_seconds(n_works, groups or _cards_product(levels, cards))
            if est > QUERY_DEADLINE_S:
                raise AnalyticsError(
                    "query_too_slow",
                    f"This query is estimated at {say_seconds(est)} ({n_works:,} works "
                    f"split {len(levels)} ways); queries get about "
                    f"{int(TIME_BUDGET_S)} seconds, so it wasn't run.",
                    "Narrow the starting set (a shorter year range, a smaller institution "
                    "or topic), split by something coarser, or drop a split.")

    body = build_body(levels, base_query, m_aggs)
    if levels and not nested and levels[0].kind == "terms":
        lv0 = levels[0]
        field0 = (lv0.agg["composite"]["sources"][0]["k"]["terms"]["field"] if lv0.composite
                  else lv0.agg["terms"]["field"])
        if lv0.selector is None and lv0.post_keep is None:
            # how many groups a single split has in all (approximate past 3,000), less
            # what a key-set filter leaves out
            body["aggs"]["n_groups"] = {"cardinality": {"field": field0,
                                                        "precision_threshold": 3000}}
            keyset = _keyset_count_agg(lv0, field0)
            if keyset is not None:
                body["aggs"]["n_keyset"] = keyset
        elif not lv0.composite and not lv0.paged_floor and not (
                lv0.post_keep is None and _count_floor_only(lv0.split.where)):
            # a calculation filter checks up to FILTERED_CANDIDATES groups: the same
            # split with nothing under it says whether more were left unchecked (a count
            # floor alone needs no check: min_doc_count applies it before the split is
            # sized, so a full list of candidates means more pass)
            t = lv0.agg["terms"]
            cand = {k: t[k] for k in ("field", "include", "exclude", "min_doc_count",
                                      "shard_size") if k in t}
            cand["size"] = FILTERED_CANDIDATES + 1
            body["aggs"]["n_candidates"] = {"terms": cand}
    # same shards for the same query, so approximate counts repeat exactly
    pref = clean_preference(json.dumps(oqo.to_dict(), sort_keys=True))
    res = _search(index_name, connection, body, deadline, "calculating the groups",
                  preference=pref)
    total_count = res["hits"]["total"]["value"]
    aggs = res.get("aggregations", {})
    check_truncated(levels, aggs)

    all_row = {"key": "all", "key_display_name": f"all {oqo.get_rows.replace('-', ' ')}",
               "count": total_count}
    for m in measures:
        if m.measure != "count":
            all_row[m.key] = _measure_value(m, aggs, total_count, None)
    all_row.pop("percent_of_those", None)   # always 100%

    group_rows: List[dict] = []
    margins: Dict[int, List[dict]] = {}
    groups_count = None
    more_groups = False
    next_cursor = None
    if levels:
        # survivors lookups (own fields checked only for groups that passed the rest)
        for idx, parts in deferred.items():
            lv = levels[idx]
            keys = sorted(_keys_at(levels, aggs, idx))
            lv.post_keep = survivors_lookup(lv, parts, keys, deadline)
        _name_conditions(levels, oqo.get_rows)
        group_rows, margins = format_levels(levels, measures, aggs, total_count, index_name)
        top = levels[0]
        filtered = (top.selector is not None or top.post_keep is not None) \
            and not top.paged_floor
        if nested:
            groups_count = len(group_rows)
        elif top.composite:
            raw = aggs["s0"]
            after = raw.get("after_key")
            if after and (len(raw["buckets"]) >= per_page or top.selector is not None):
                next_cursor = _encode_cursor(after["k"])
            more_groups = next_cursor is not None
            groups_count = _groups_count(top, aggs)
        elif top.kind == "terms" and not filtered:
            # one page of groups straight from ES, in its order; a sort ES can't do
            # (percent) reorders that page
            if sort and sort_measure is None:
                group_rows = _sort_rows(group_rows, sort)
            start = (page - 1) * per_page
            n_rows = len(group_rows)
            group_rows = group_rows[start:start + per_page]
            if top.paged_floor:
                # how many groups pass the count isn't known on this path
                more_groups = n_rows > page * per_page
            else:
                more_groups = bool(aggs["s0"].get("sum_other_doc_count"))
                groups_count = _groups_count(top, aggs)
        elif _filter_truncated(top, aggs):
            # more groups than the filter checked: the first FILTERED_CANDIDATES by count
            # are exact when a count floor is the whole filter and the sort is by count
            if (top.post_keep is None and _count_floor_only(top.split.where)
                    and sort in (None, ("count", "desc"))):
                start = (page - 1) * per_page
                group_rows = group_rows[start:start + per_page]
                more_groups = True
            else:
                raise AnalyticsError(
                    "too_many_groups",
                    f"More than {FILTERED_CANDIDATES:,} {_split_noun(top)} groups are left "
                    f"to check against the group filter; a filtered split checks up to "
                    f"{FILTERED_CANDIDATES:,}.",
                    f"Add a count filter or raise it ({count_fix(top)}), or narrow the "
                    f"starting set.")
        else:
            # every group is here: sort and page in Python
            if sort:
                group_rows = _sort_rows(group_rows, sort)
            groups_count = len(group_rows)
            if top.kind == "terms":
                start = (page - 1) * per_page
                group_rows = group_rows[start:start + per_page]
                more_groups = start + per_page < groups_count

    if levels:
        deadline.mark("naming the groups")
        group_rows = name_rows(levels, group_rows, connection)   # the page only
        margins = {i: name_rows(levels, rs, connection) for i, rs in margins.items()}
        if nested:
            groups_count = len(group_rows)
    if group_rows:
        fill_own_values(levels, group_rows, measures, deadline)   # the page only
    for i, rs in margins.items():
        fill_own_values(levels, rs, measures, deadline, start_level=i)
    for m in measures:
        if m.measure == "value":
            all_row.pop(m.key, None)   # a group's own field has no whole-set value
    summary = {"all": all_row}
    if nested:
        # each split's groups on their own, computed from the works (never summed
        # from group rows): the outer split is the top level of group_by
        summary["splits"] = [{"groups": [{k: v for k, v in r.items() if k != "groups"}
                                         for r in group_rows], "more_groups": False}]
        for lv in levels[1:]:
            buckets = aggs.get(f"m{lv.index}", {}).get("buckets")
            summary["splits"].append({
                "groups": margins.get(lv.index, []),
                # a terms split sized for the nested request came back full: more groups
                # exist over the whole set than the summary lists
                "more_groups": bool(lv.kind == "terms" and lv.size and isinstance(buckets, list)
                                    and len(buckets) >= lv.size)})
    meta = {
        "count": total_count,
        "db_response_time_ms": res.get("took"),
        "page": page if levels else None,
        "per_page": per_page if levels else None,
        "groups_count": groups_count,
        "more_groups": more_groups,
        "next_cursor": next_cursor,
        "measures": [_measure_meta(m, oqo.get_rows) for m in measures],
        "splits": [split_meta(g, oqo.get_rows) for g in oqo.group_by],
        "es_calls": deadline.calls,
        "elapsed_ms": deadline.elapsed_ms(),
        "steps": deadline.log,
        "cost": price(oqo),
    }
    return {"meta": meta, "summary": summary, "group_by": group_rows, "results": []}


def _encode_cursor(key) -> str:
    import base64
    return "g1." + base64.urlsafe_b64encode(json.dumps(key).encode()).decode().rstrip("=")


def _decode_cursor(cursor: str):
    import base64
    try:
        if not cursor.startswith("g1."):
            raise ValueError
        raw = cursor[3:]
        return json.loads(base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4)))
    except Exception:
        raise AnalyticsError("invalid_cursor", "That cursor isn't one this query gave out.",
                             "Start again with cursor=*, then pass each next_cursor.")


def _keys_at(levels: List[Level], aggs: dict, idx: int) -> set:
    out = set()

    def walk(level_i, agg):
        lv = levels[level_i]
        for k, b in _bucket_rows(lv, agg):
            if level_i == idx:
                out.add(k if lv.kind == "terms" else lv.labels[k][0])
            elif f"s{level_i + 1}" in b:
                walk(level_i + 1, b[f"s{level_i + 1}"])

    walk(0, aggs["s0"])
    if f"m{idx}" in aggs:   # the split on its own (the summary) has groups of its own
        lv = levels[idx]
        out |= {k if lv.kind == "terms" else lv.labels[k][0]
                for k, _ in _bucket_rows(lv, aggs[f"m{idx}"])}
    return {k for k in out if isinstance(k, str)}


# ---------------------------------------------------------------------------
# Price and the free check (`/query`): validity, limits, time, cost
# ---------------------------------------------------------------------------
CREDIT_USD = 0.0001       # 10,000 credits = $1 (the proxy's creditsToUsd)
RERANK_CREDITS = 10       # the proxy's RERANK_CREDITS
# Every OQL query priced like the API (Jason, 2026-10-03). Off until the proxy
# discounts the website's facet calls (#1533), then OQL_PRICE_ALL=true on both apps.
PRICE_ALL_OQL = os.environ.get("OQL_PRICE_ALL", "false").lower() == "true"
SEARCH_CREDITS = 10       # what one search costs on its own (the proxy's search price)
LOOKUP_CREDITS = 1        # one extra call to look up groups
TIME_BUDGET_S = 10.0      # the check refuses plans estimated over this (Jason, 2026-10-03)

# Measured rates (#1512 work/engine_capabilities.md, 2026-10-02/03): one aggregation
# over an id-defined set up to ~1M works 0.1-0.6 s; over a title-abstract search set
# 2.6-3.0 s per call; 15 ms per listed search; own-field lookups 0.1-0.4 s after a
# count filter; listing ids about 40,000 a second; co-author sets 0.4-3 s.
EST_CALL_ID_SET_S = 0.6
EST_CALL_SEARCH_SET_S = 3.0
EST_PER_LISTED_SEARCH_S = 0.015
EST_LOOKUP_S = 0.4
EST_COAUTHOR_S = 1.5
EST_IDS_PER_S = 40_000
EST_NAMES_S = 0.6
# The main request over big sets: about (works / 1e8) x (1 + groups / 5,000) seconds
# (fitted to the three measurements in check()).
EST_WORKS_PER_S = 100_000_000
EST_GROUPS_SCALE = 5_000


def _tree_has_search(node) -> bool:
    if isinstance(node, LeafFilter):
        return isinstance(node.column_id, str) and ".search" in node.column_id
    if isinstance(node, BranchFilter):
        return any(_tree_has_search(c) for c in node.filters)
    return False


def plain_price(oqo: OQO, reranked: bool = False, grandfathered: bool = False,
                website: bool = False) -> dict:
    """A query with no pipeline features costs what the same query costs as a URL
    (Jason, 2026-10-03: OQL priced like the API): a search 10 (semantic included; 1
    for a grandfathered key), grouped or not; anything else 1. The website's facets
    (a group by the proxy marks as the website's) stay at 1. A rerank that ran
    adds 10."""
    search = any(_tree_has_search(f) for f in oqo.filter_rows)
    if oqo.group_by and website:
        credits, what = 1, "a website facet"
    elif search and grandfathered:
        credits, what = 1, "a search (grandfathered key)"
    elif search:
        credits, what = 10, "a search"
    else:
        credits, what = 1, "a group by" if oqo.group_by else "a list"
    steps = [{"credits": credits, "what": what}]
    if reranked:
        credits += RERANK_CREDITS
        steps.append({"credits": RERANK_CREDITS, "what": "rerank"})
    return {"credits": credits, "usd": round(credits * CREDIT_USD, 6), "steps": steps}


def price(oqo: OQO) -> dict:
    """Credits from the query plan (Jason, 2026-10-03: price from the plan; each
    searched phrase costs what that search costs alone). The starting set costs what
    a list (1) or a search (10) costs; each listed search or condition with a search
    adds a search; each lookup call adds 1."""
    steps = []
    base_search = any(_tree_has_search(f) for f in oqo.filter_rows)
    steps.append({"what": "the starting set" + (" (a search)" if base_search else ""),
                  "credits": SEARCH_CREDITS if base_search else 1})
    for i, g in enumerate(oqo.group_by):
        n = 0
        if g.values is not None and g.column_id and g.column_id.endswith(".search"):
            n = len(g.values)
        elif g.conditions is not None:
            n = sum(1 for c in g.conditions if _tree_has_search(c))
        if n:
            steps.append({"what": f"split {i + 1}: {n} search{'es' if n > 1 else ''}",
                          "credits": n * SEARCH_CREDITS})
        if g.where is not None:
            lookups = _lookup_kinds(g.where)
            if lookups:
                steps.append({"what": f"split {i + 1}: {len(lookups)} lookup"
                                      f"{'s' if len(lookups) > 1 else ''} ({', '.join(lookups)})",
                              "credits": len(lookups) * LOOKUP_CREDITS})
    if any(m.measure == "value" for m in oqo.calculate):
        steps.append({"what": "the groups' own fields (a lookup)", "credits": LOOKUP_CREDITS})
    credits = sum(s["credits"] for s in steps)
    return {"credits": credits, "usd": round(credits * CREDIT_USD, 6), "steps": steps}


def export_price(query_price: dict, rows: int) -> dict:
    """What a download of `rows` rows costs: the query's price for every ROWS_PER_PRICE
    rows, like works exports (Jason, 2026-10-08; at least one unit, so an empty file
    costs what the query costs)."""
    units = max(1, -(-rows // ROWS_PER_PRICE))
    credits = query_price["credits"] * units
    return {"credits": credits, "usd": round(credits * CREDIT_USD, 6),
            "steps": query_price.get("steps", []) + [
                {"what": f"x {units} for {rows:,} rows (the query's price per "
                         f"{ROWS_PER_PRICE} rows)", "credits": credits - query_price["credits"]}]}


def pages_by_cursor(oqo: OQO, fields_dict, index_name: str) -> bool:
    """A single split by a column (terms) pages through any number of groups with a
    cursor; anything else (no split, nested splits, listed values, searches,
    conditions, bins, yes/no) returns all its groups at once."""
    if len(oqo.group_by) != 1:
        return False
    try:
        return build_level(0, oqo.group_by[0], oqo, fields_dict, index_name).kind == "terms"
    except Exception:
        return False


def _lookup_kinds(where) -> List[str]:
    """The extra calls a group filter needs: co-author / collaborator sets and the
    group's own fields (one lookup each); ids and collections ride along free."""
    parts = where.filters if (isinstance(where, BranchFilter) and where.join == "and"
                              and not where.is_negated) else [where]
    kinds = []
    for p in parts:
        if _has_measure(p):
            continue
        cols = set()

        def walk(n):
            if isinstance(n, (LeafFilter, AffiliationFilter)):
                cols.add(n.column_id)
            elif isinstance(n, BranchFilter):
                for c in n.filters:
                    walk(c)
        walk(p)
        if cols <= {"ids.openalex", "collection"}:
            continue
        if cols <= {"co_author"}:
            kinds.append("co-authors")
        elif cols <= {"collaborator"}:
            kinds.append("collaborators")
        else:
            kinds.append("the groups' own fields")
    return kinds


def check(oqo: OQO, *, index_name: str, connection, fields_dict, base_query: dict,
          deadline: Optional[Deadline] = None) -> dict:
    """The free check: every limit the query hits (with its fix), the estimated
    time against the 10-second budget, and the price. Runs only cheap probes (the
    group guard's distinct counts, a count of an own-field filter's matches);
    never the query itself."""
    deadline = deadline or Deadline()
    oqo = _nnf_group_filters(oqo)
    limits: List[dict] = []
    base_search = any(_tree_has_search(f) for f in oqo.filter_rows)
    call_s = EST_CALL_SEARCH_SET_S if base_search else EST_CALL_ID_SET_S
    est = call_s
    calls = 1
    levels: List[Level] = []
    try:
        levels = [build_level(i, g, oqo, fields_dict, index_name)
                  for i, g in enumerate(oqo.group_by)]
    except AnalyticsError as e:
        limits.append(e.to_dict())
    except APIQueryParamsError as e:
        limits.append({"error": "invalid_query", "message": str(e), "fix": ""})
    nested = len(levels) > 1
    for g in oqo.group_by:
        if g.values is not None and g.column_id and g.column_id.endswith(".search"):
            est += EST_PER_LISTED_SEARCH_S * len(g.values)
    for lv in levels:
        where = lv.split.where
        if where is None:
            continue
        try:
            m_parts, k_parts = _split_where(where)
        except AnalyticsError as e:
            limits.append(e.to_dict())
            continue
        for p in k_parts:
            kinds = _lookup_kinds(p)
            if not kinds:
                continue
            calls += 1
            if kinds[0] in ("co-authors", "collaborators"):
                est += EST_COAUTHOR_S
            elif m_parts:
                est += EST_LOOKUP_S       # survivors of the count filter
            else:
                # the reverse lookup: how many of the group entity match?
                try:
                    _es_tree(p)        # what the run refuses, the check says (`not at ... since`)
                except AnalyticsError as e:
                    limits.append(e.to_dict())
                    continue
                n = _count_entity_matches(lv, p, deadline)
                if n is None:
                    continue
                n_keys = None
                if n > LOOKUP_LIMIT and lv.kind == "terms":
                    # the works side: the groups the works have, checked in their records
                    try:
                        n_keys = _works_side_count(lv, index_name, connection, base_query, deadline)
                    except AnalyticsError:
                        pass
                if n_keys is not None and n_keys <= WORKS_SIDE_LIMIT:
                    est += 0.4 + n_keys / 36_000
                    calls += 2 + n_keys // 10_000
                elif n > LOOKUP_LIMIT:
                    limits.append(_both_sides_too_big(lv, n, n_keys).to_dict())
                else:
                    est += 0.2 + n / EST_IDS_PER_S
    # One probe: how many works the set holds and how many distinct values each split
    # by a column takes. The main request's time grows with both (measured 2026-10-03:
    # 2020+ topic x year, 104M works and 32K groups, 8 s; MIT's year x type x OA, 0.4M
    # works and 4K groups, 0.4 s; field x year over 256M works, 0.5 s).
    n_works, cards, groups = None, {}, None
    try:
        n_works, cards = _probe(levels, index_name, connection, base_query, deadline)
        if nested:
            calls += 1                       # the run probes the splits too
            plan_levels(levels, cards, True, DEFAULT_PER_PAGE, 1, None)
            before = deadline.calls
            groups = guard_nested(levels, cards, index_name, connection, base_query,
                                  deadline)
            calls += deadline.calls - before
        elif levels:
            lv = levels[0]
            groups = cards.get(lv.index) if lv.kind == "terms" else max(len(lv.order_keys), 1)
    except AnalyticsError as e:
        limits.append(e.to_dict())
    if n_works is not None:
        if nested and groups is None:
            groups = _cards_product(levels, cards)   # count-filtered: all groups are counted
        est += max(0.0, estimate_main_seconds(n_works, groups or 1) - EST_CALL_ID_SET_S)
        if nested:
            est += call_s                    # the probe the run makes first
    est += EST_NAMES_S if levels else 0
    if any(m.measure == "value" for m in oqo.calculate):
        est += EST_LOOKUP_S
        calls += 1
    estimate = {"seconds": round(est, 1), "es_calls": calls,
                "budget_seconds": TIME_BUDGET_S, "within_budget": est <= TIME_BUDGET_S}
    if any(x["error"] in ("query_too_slow", "too_many_groups") for x in limits):
        estimate["within_budget"] = False
    if est > TIME_BUDGET_S and not any(x["error"] == "query_too_slow" for x in limits):
        limits.append({
            "error": "query_too_slow",
            "message": (f"This query is estimated at {say_seconds(est)}; queries get about "
                        f"{int(TIME_BUDGET_S)} seconds."),
            "fix": ("Narrow the starting set, list fewer searches, or add a count filter "
                    "before filters on the groups' own fields."),
        })
    return {"valid": not limits, "limits": limits, "estimate": estimate, "cost": price(oqo)}


def _count_entity_matches(lv: Level, part, deadline: Deadline,
                          extra: Optional[dict] = None) -> Optional[int]:
    from query_translation.oqo_to_es import _translate
    from core.join_resolver import entity_index
    from elasticsearch_dsl.connections import get_connection
    try:
        g_fields, g_index = entity_index(lv.group_entity)
        q = _translate(_es_tree(part), g_fields).to_dict()
    except Exception:
        return None
    filters = [q] + ([{"range": {"works_count": {"gt": 0}}}]
                     if lv.group_entity == "authors" else []) + ([extra] if extra else [])
    body = {"size": 0, "track_total_hits": True,
            "query": {"bool": {"filter": filters}}}
    try:
        res = get_connection().search(
            index=g_index, body=body,
            request_timeout=deadline.timeout("counting the groups' own-field matches"))
    except ConnectionTimeout:
        return None
    return res["hits"]["total"]["value"]


def _measure_meta(m: Measure, entity: str) -> dict:
    from query_translation.oql_pipeline import measure_text
    return {"key": m.key, "measure": m.measure, "column_id": m.column_id,
            "oql": measure_text(m, entity.replace("-", " "))}
