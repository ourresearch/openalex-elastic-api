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
import random
import re
import time
from bisect import bisect_right
from dataclasses import dataclass, field, replace
from typing import Any, Dict, List, Optional, Tuple

from elasticsearch.exceptions import ConnectionTimeout, TransportError
from elasticsearch_dsl import Q, Search

from core.exceptions import APIQueryParamsError
from core.group_by.buckets import SINGLE_LIST_SHARD_SIZE, _MAP_HINT_FIELDS
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
DEFAULT_PER_PAGE = 200
MAX_PAGE_DEPTH = 10_000        # page x per_page on a single split
# a sort ES can't do (a percent, a group's own field) reads every group of a single split
# and sorts them all, up to this many groups; past it, a loud error (oxjob #1555)
ALL_GROUPS_SORT_LIMIT = 10_000
CSV_PAGE_GROUPS = 10_000       # groups in one page of an export (format=csv with a cursor, #1550)
ROWS_PER_PRICE = 100           # an export costs the query's price per 100 rows, like works (#1550)
# A cursor page over a big set reads only the works holding its next keys (oxjob #1598): a range on the split's
# key, bounded by the field's own sorted term list, instead of every work in the set (a 10,000-author page over
# all 328M works: 6.9 s read whole, 0.4 s on its range; EXPLORE.md in the job).
PARTITION_MIN_WORKS = int(os.environ.get("OQL_PARTITION_MIN_WORKS", "2000000"))
PARTITION_MIN_TERMS = 1_000     # keys listed for one range, at least
PARTITION_MAX_TERMS = 100_000   # and at most (terms-enum lists 50,000 in 0.4 s)
PARTITION_RESERVE_S = 5.0       # a page stops reading keys when less than this is left of its deadline (naming
                                # 10,000 sources takes ~4 s), and returns what it has
KEYSET_CHUNK = 10_000           # a split filtered to a key set (`by journal`, `by institution in [Canada](CA)`) pages
                                # through its own sorted keys, this many at most in one terms filter
ID_PREFIX = "https://openalex.org/"


class AnalyticsError(APIQueryParamsError):
    """A loud, fixable refusal: `code`, a message and the fix."""

    def __init__(self, code: str, message: str, fix: str, status: int = 400,
                 too_big: bool = False, groups: Optional[int] = None):
        super().__init__(f"{message} {fix}")
        self.code = code
        self.message = message
        self.fix = fix
        self.status = status
        # a nested split too big for one answer (oxjob #1598): it pages instead when it can
        # (`_nested_big`); `groups` is the estimated combinations when the refusal counted them
        self.too_big = too_big
        self.groups = groups

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
    from query_translation.oql_core import THING_NOUNS
    thing = THING_NOUNS.get(lv.column_id) if lv is not None and lv.column_id else None
    # the table sentence's floor (oxjob #1555 D2, 2026-10-20)
    return f"`Only {thing or '...'} with more than {n:,} works ...`"


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
    from core.utils import get_field
    return get_field(fields_dict, column_id).query_for("true")


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


def _is_count_floor(p) -> bool:
    """`count >` / `count >=` (terms min_doc_count)."""
    return isinstance(p, MeasureFilter) and p.measure == "count" and not p.is_negated and p.operator in (">", ">=")


def _count_floor_only(where) -> bool:
    """The group filter is only `count >` / `count >=`: terms min_doc_count applies it
    before the split is sized, so the split's first groups by count are exact."""
    if where is None:
        return False
    m_parts, k_parts = _split_where(where)
    return bool(m_parts) and not k_parts and all(_is_count_floor(p) for p in m_parts)


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
        keys = lv.kept_keys()
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
        if not lv.kept_keys():
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
    works_filters: List[dict] = field(default_factory=list)  # own fields pushed down (#1617; first split only)
    all_groups: bool = False                   # read every group: a sort ES can't do (#1555)
    name_vocab: Optional[dict] = None          # codes sorted by name, not code (#1658)
    key_kind: str = "keyword"                  # how a terms split's keys compare: keyword | number | date
    _kept: Optional[tuple] = field(default=None, repr=False, compare=False)

    def kept_keys(self) -> Optional[List]:
        """The keys a key-set filter with an include list keeps, sorted (None without one). Sorted once per include
        / exclude pair (a 250,000-id set takes ~60 ms, and a page reads it several times); both are replaced, never
        changed in place."""
        if self.include is None:
            return None
        if self._kept is None or self._kept[0] is not self.include or self._kept[1] is not self.exclude:
            self._kept = (self.include, self.exclude, sorted(self.include - (self.exclude or set())))
        return self._kept[2]

    def keeps(self, k) -> bool:
        """Is group key `k` in this split's key set (always, without one)?"""
        return (self.include is None or k in self.include) and not (self.exclude and k in self.exclude)


def _keyset_terms(lv: "Level") -> dict:
    """A split's key set as terms include / exclude (an empty include list keeps nothing)."""
    kept = lv.kept_keys()
    if kept is not None:
        return {"include": kept or ["__none__"]}
    return {"exclude": sorted(lv.exclude)} if lv.exclude else {}


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


def _row_key(k, lv: "Level", index_name: str) -> str:
    """A group row's key, the same whether the split came from the terms or from listed
    values (`13` -> `https://openalex.org/fields/13`, as a plain split by field writes it)."""
    from core.group_by.results import format_key
    key = format_key(k, lv.column_id, index_name) if isinstance(k, str) else str(k)
    if (isinstance(k, (int, float)) or (isinstance(k, str) and k.isdigit())) \
            and "openalex.org" not in key and lv.column_id \
            and lv.column_id.endswith(".id") and lv.group_entity:
        key = f"{ID_PREFIX}{lv.group_entity}/{k}"
    return key


def build_level(i: int, g: GroupBy, oqo: OQO, fields_dict, index_name: str) -> Level:
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
    if ftype == "BooleanField":
        # the same true/false queries the filter and group_by run (oxjob #1859)
        lv = Level(i, g, "filters", column_id=column_id)
        lv.agg = {"filters": {"filters": {"true": fld.query_for("true").to_dict(),
                                          "false": fld.query_for("false").to_dict()}}}
        lv.labels = {"true": ("true", _label_bool(column_id, True)),
                     "false": ("false", _label_bool(column_id, False))}
        lv.order_keys = ["true", "false"]
        return lv
    es_field = fld.alias if getattr(fld, "alias", None) else fld.es_sort_field()
    lv = Level(i, g, "terms", column_id=column_id, group_entity=group_entity,
               name_vocab=_name_vocab(column_id, oqo.get_rows),
               key_kind="date" if "Date" in ftype else ("number" if ftype == "RangeField" else "keyword"))
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
def _has_own_fields(entity: str) -> bool:
    """Can a split's groups be filtered on their own records? Not every group entity has a lookup: a split by cited
    work (works, #1513) answered a 500 on `entity_index` (Sentry OPENALEX-ELASTIC-API-2A, 2026-10-28)."""
    from core.join_resolver import entity_index
    try:
        entity_index(entity)
        return True
    except ValueError:
        return False


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


# -- the smaller side (oxjob #1555, thing-first) --
# `at [UBC](I141945490) since 2022` is one terms query on the authors' institution-year
# keys (#1617, oqo_to_es.affiliation_query), like any other own field.
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


# A split by a link each work has at most once (its primary source, its primary
# topic): a condition on the group's own fields is a condition on the works' copy of
# them, so it runs as a works filter and the groups need no lookup (#1617: journals
# cited by KU's 2024+ works listed, checked and filtered 25,000 sources, 6 s of 10).
# Only fields whose works copy matches the group's own value: measured on 3,000
# sources and their 4.56M works (2026-10-10), type, is_in_doaj, is_core and
# host_organization matched exactly; is_oa did not (181 sources: the works' value
# varies by work) nor did listed_in (177: the works' copy lags, #1615); a topic's
# place in the taxonomy is fixed.
_PUSHDOWN = {
    "primary_location.source.id": {"type", "is_in_doaj", "is_core", "host_organization"},
    "primary_topic.id": {"field.id", "subfield.id", "domain.id"},
}


def _pushdown(lv: Level, part, fields_dict) -> Optional[dict]:
    """`part` (a condition on the groups' own fields) as a filter on the works, when the split is the first (the only
    split, or a nested one's leading split: its groups' works are the ones whose single link passes, oxjob #1598), by
    a single-valued link, and every field in it has a works copy. The caller reads only that split's groups through
    it, never the whole-set row or the other splits on their own. A split by a link after a small one (`by
    <listed values> and journal`) keeps its key-set lookup."""
    from query_translation.oqo_to_es import _translate
    if lv.index != 0:
        return None
    link = lv.agg.get("terms", {}).get("field")
    allowed = _PUSHDOWN.get(link)
    if allowed is None:
        return None
    prefix = link[:-len("id")]

    def move(node):
        if isinstance(node, LeafFilter) and node.column_id in allowed \
                and isinstance(node.value, (str, int, float, bool)):
            return replace(node, column_id=prefix + node.column_id)
        if isinstance(node, BranchFilter):
            kids = [move(c) for c in node.filters]
            return None if None in kids else replace(node, filters=kids)
        return None
    moved = move(part)
    q = _translate(moved, fields_dict) if moved is not None else None
    return q.to_dict() if q is not None else None


def resolve_keysets(lv: Level, parts: List, oqo: OQO, works_index: str, connection,
                    deadline: Deadline, has_measure_filter: bool,
                    base_query: Optional[dict] = None, works_fields=None) -> List:
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
        pushed = _pushdown(lv, p, works_fields)
        if pushed is not None:
            lv.works_filters.append(pushed)
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
        # authors), or the groups the works have, checked against their own fields (the
        # kelp works' authors), whichever is fewer; loud when both are too many.
        n_keys = (_works_side_count(lv, works_index, connection, base_query, deadline)
                  if base_query is not None and lv.kind == "terms" else None)
        n_own = _count_entity_matches(lv, p, deadline)
        ids = None
        if n_keys is None or n_own is None or n_own <= n_keys:
            g_fields, _g_index = entity_index(lv.group_entity)
            q = _translate(p, g_fields)
            extra = [Q("range", works_count={"gt": 0})] if lv.group_entity == "authors" else []
            q_all = Q("bool", filter=[q] + extra) if extra else q
            ids = resolve_query_ids(lv.group_entity, q_all,
                                    json.dumps(p.to_dict(), sort_keys=True), LOOKUP_LIMIT,
                                    request_timeout=deadline.timeout("looking up the groups' own fields"))
        if ids is None and n_keys is not None and n_keys <= WORKS_SIDE_LIMIT:
            # list the works' groups and check their own fields side by side, as a walk does
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
    filters = [_translate(p, g_fields).to_dict() for p in parts]
    keep = set()
    es = get_connection()
    # a plain id-filtered search, 10,000 ids a call (a composite over the 100M-row
    # authors index took 3 s for 495 ids; this takes about 0.1 s)
    for start in range(0, len(keys), 10_000):
        chunk = keys[start:start + 10_000]
        body = {"size": len(chunk), "_source": ["id"],
                "query": {"bool": {"filter": [{"terms": {"id": chunk}}] + filters}}}
        try:
            res = es.search(index=g_index, body=body,
                            request_timeout=deadline.timeout("checking the groups' own fields"))
        except ConnectionTimeout:
            raise too_slow("checking the groups' own fields")
        keep |= {h["_source"]["id"] for h in res["hits"]["hits"]}
    return keep


# ---------------------------------------------------------------------------
# Running
# ---------------------------------------------------------------------------
def _search(index, connection, body, deadline: Deadline, what: str, **params) -> dict:
    from elasticsearch_dsl.connections import get_connection
    from query_translation import id_split
    es = get_connection(connection)

    def one(b):
        return es.search(index=index, body=b, request_timeout=deadline.timeout(what), **params)
    try:
        # a big id filter (a set in parentheses) runs in pieces side by side (#1617)
        return id_split.search(one, body) or one(body)
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
                "number of groups.", too_big=True)
        raise


def _cardinalities(levels: List[Level], index, connection, base_query, deadline) -> Dict[int, int]:
    """The group guard's estimate: distinct keys of each terms split in the set."""
    return _probe(levels, index, connection, base_query, deadline)[1]


def _probe(levels: List[Level], index, connection, base_query, deadline) -> Tuple[int, Dict[int, int]]:
    """(works in the set, distinct keys of each terms split): one cheap request."""
    terms = [lv for lv in levels if lv.kind == "terms"]

    def card(lv):
        c = {"cardinality": {"field": lv.agg["terms"]["field"], "precision_threshold": 3000}}
        # own fields pushed down to the works (`by journal`) narrow the split's groups
        return {"filter": _and(*lv.works_filters), "aggs": {"c": c}} if lv.works_filters else c
    aggs = {f"card{lv.index}": card(lv) for lv in terms}
    body = {"size": 0, "track_total_hits": True, "query": base_query}
    if aggs:
        body["aggs"] = aggs
    res = _search(index, connection, body, deadline, "counting the groups")
    cards = {lv.index: res["aggregations"][f"card{lv.index}"] for lv in terms}
    return res["hits"]["total"]["value"], {i: a.get("c", a)["value"] for i, a in cards.items()}


def _and(*queries) -> dict:
    """Every query given (empty ones skipped), as one bool filter."""
    return {"bool": {"filter": [q for q in queries if q]}}


def _lead_query(levels: List[Level], base_query: dict) -> dict:
    """The works the leading split's groups hold: the set, narrowed by its own fields pushed down (`by journal`:
    works whose primary source is a journal). The whole-set row and the other splits on their own read every work."""
    wf = levels[0].works_filters if levels else []
    return _and(base_query, *wf) if wf else base_query


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


def _cap_cards(cards: Dict[int, int], sizes: Dict[int, Optional[int]]) -> None:
    """A split filtered to a key set holds at most its own keys (`by institution in [Canada](CA)`: 4,641 of the
    100K+ institutions the works hold): the probe counts every key the works hold."""
    for i, n in sizes.items():
        if i in cards and n is not None:
            cards[i] = min(cards[i], n)


def _combo_card(fields: List[str], precision: int) -> dict:
    """A cardinality of the combined keys of `fields` (`_COMBO_SCRIPT`)."""
    return {"script": {"source": _COMBO_SCRIPT, "params": {"fields": fields}}, "precision_threshold": precision}


# The combined-keys script builds every combination of every work (~0.25 s a million works, but 2.8 s for MIT's
# 14,000 works of 2023, whose hyper-authored papers hold millions each; 7 s for all 10.9M works of 2023, 2026-10-27):
# past this many works the count comes from a sample of the leading split's keys instead (oxjob #1598, EXPLORE § 9).
COMBO_SCRIPT_MAX_WORKS = 2_000_000
SAMPLE_KEYS = 5_000             # leading keys in the sample, about


def _inner_card(fields: List[str]) -> dict:
    """The distinct keys (combined keys, past one) of the splits under a sampled key."""
    return {"field": fields[0], "precision_threshold": 100} if len(fields) == 1 else _combo_card(fields, 100)


def _sampled_combos(fields: List[str], lead_card: int, index, connection, base_query, deadline) -> int:
    """About how many combined keys `fields` take, from one hash partition of the leading field's keys (terms
    `include.partition`: a uniform sample of about SAMPLE_KEYS keys whatever their order or size): each sampled
    key's distinct inner keys, summed, times the partitions. Measured 2026-10-27 on production: 2023 institution x
    author 69.4M against the true 72.2M (0.8 s); all works by institution and author 589M (2.8 s), by author and
    year 295M (4.1 s). A few huge keys in or out of the sample move it most (0.79x at 4,366 institutions)."""
    parts = max(1, lead_card // SAMPLE_KEYS)
    card = _inner_card(fields[1:])
    body = {"size": 0, "query": base_query, "aggs": {"k": {
        "terms": {"field": fields[0], "size": 65_000,
                  "include": {"partition": 0, "num_partitions": parts}},
        "aggs": {"c": {"cardinality": card}}}}}
    res = _search(index, connection, body, deadline, "estimating the combined groups")
    return int(sum(b["c"]["value"] for b in res["aggregations"]["k"]["buckets"]) * parts)


def _keyset_combos(ks: Level, others: List[Level], index, connection, base_query, deadline) -> int:
    """About how many combined keys a split filtered to a key set takes with the other splits by a column: each
    of its keys' distinct other keys, summed (a combination's count doesn't depend on the splits' order), from a
    fixed sample of SAMPLE_KEYS of its keys scaled to all of them. The other splits' own key sets aren't applied,
    so with two of them this is an upper bound."""
    keys = ks.kept_keys()
    if not keys:
        return 0
    sample = keys if len(keys) <= SAMPLE_KEYS else random.Random(0).sample(keys, SAMPLE_KEYS)
    field = ks.agg["terms"]["field"]
    body = {"size": 0, "query": _and(base_query, {"terms": {field: sample}}), "aggs": {"k": {
        "terms": {"field": field, "size": len(sample), "include": sample},
        "aggs": {"c": {"cardinality": _inner_card([lv.agg["terms"]["field"] for lv in others])}}}}}
    res = _search(index, connection, body, deadline, "estimating the combined groups")
    return int(sum(b["c"]["value"] for b in res["aggregations"]["k"]["buckets"]) * len(keys) / len(sample))


def _combined_groups(levels: List[Level], index, connection, base_query, deadline,
                     n_works: Optional[int] = None, cards: Optional[Dict[int, int]] = None) -> int:
    """Estimated groups of a nested split: the distinct combined keys of its terms
    splits, times the group count of its other splits (listed values, bins). Over a
    big set (more than COMBO_SCRIPT_MAX_WORKS) the combined keys come from a sample;
    a split filtered to a key set counts from a sample of its own keys. The combinations live under the leading
    split's groups, so its own fields pushed down to the works narrow them."""
    base_query = _lead_query(levels, base_query)
    terms = [lv for lv in levels if lv.kind == "terms"]
    fields = [lv.agg["terms"]["field"] for lv in terms]
    other = 1
    for lv in levels:
        if lv.kind == "filters":
            other *= max(len(lv.order_keys), 1)
        elif lv.kind == "range":
            other *= max(len(lv.order_keys), 1)
        elif lv.kind == "histogram":
            other *= 100
    if len(fields) == 1 and cards and cards.get(terms[0].index):
        return cards[terms[0].index] * other
    ks = next((lv for lv in terms if lv.include is not None), None)
    if ks is not None and len(terms) > 1:
        return _keyset_combos(ks, [lv for lv in terms if lv is not ks], index, connection, base_query,
                              deadline) * other
    if len(fields) > 1 and n_works is not None and n_works > COMBO_SCRIPT_MAX_WORKS \
            and cards and cards.get(terms[0].index):
        return _sampled_combos(fields, cards[terms[0].index], index, connection, base_query,
                               deadline) * other
    body = {"size": 0, "query": base_query, "aggs": {"combo": {"cardinality": _combo_card(fields, 1000)}}}
    res = _search(index, connection, body, deadline, "counting the combined groups")
    return int(res["aggregations"]["combo"]["value"]) * other


def guard_nested(levels: List[Level], cards: Dict[int, int], index, connection,
                 base_query, deadline, n_works: Optional[int] = None) -> Optional[int]:
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
        n = _combined_groups(levels, index, connection, base_query, deadline, n_works, cards)
    if n > MAX_RESPONSE_BUCKETS:
        names = " x ".join(_split_noun(lv) for lv in levels)
        raise AnalyticsError(
            "too_many_groups",
            f"Splitting by {names} gives about {n:,} groups together; one answer holds "
            f"up to {MAX_RESPONSE_BUCKETS:,}.",
            "Narrow the starting set (a shorter year range), split by something coarser "
            "(field instead of topic), or drop a split: one split pages through any "
            "number of groups.", too_big=True, groups=n)
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
            "Raise the count threshold, narrow the starting set, or make it the only split.",
            too_big=True)
    return keys


def _cards_product(levels: List[Level], cards: Optional[Dict[int, int]]) -> int:
    p = 1
    for lv in levels:
        p *= 100 if lv.kind == "histogram" else max(_level_groups(lv, cards) or 1, 1)
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
                "split.", too_big=True)
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
                    "through any number of groups).", too_big=True)
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
        elif lv.all_groups:
            # every group, so the sort covers them all; one past the limit says the
            # estimate was short (checked after the request)
            size = min(int((card or 0) * 1.1) + 10, ALL_GROUPS_SORT_LIMIT + 1)
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
        # a single split takes deep shard lists at any size, as on the URL path
        # (buckets.determine_shard_size, oxjob #1513)
        terms["shard_size"] = max(size * 2, 3000 if nested else SINGLE_LIST_SHARD_SIZE)
        if terms.get("field") in _MAP_HINT_FIELDS:
            terms["execution_hint"] = "map"   # as on the URL path: 10 s -> ~1 s
        lv.size = size
        order = [{"_count": "desc"}, {"_key": "asc"}]
        if sort_measure and not nested and (lv.selector is None or lv.paged_floor):
            order = ((sort_measure if isinstance(sort_measure, list) else [sort_measure])
                     + [{"_key": "asc"}])
        terms["order"] = order
        terms.update(_keyset_terms(lv))
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


def level_rows(levels: List[Level], measures: List[Measure], level_i: int, agg: dict, parent_count: Optional[int],
               index_name: str) -> List[dict]:
    """One level's aggregation result as rows, unnamed, with the levels under it (`s<i+1>` in each bucket)."""
    def rows(level_i: int, agg: dict, parent_count: int) -> List[dict]:
        lv = levels[level_i]
        out = []
        for k, b in _bucket_rows(lv, agg):
            count = b["doc_count"]
            if lv.kind == "terms":
                if lv.post_keep is not None and k not in lv.post_keep:
                    continue
                if lv.composite and not lv.keeps(k):
                    continue   # composite has no include/exclude
                key = _row_key(k, lv, index_name)
                label, raw = None, k
            elif lv.kind == "filters":
                key, label, raw = _small_key(lv, k, index_name)
                if lv.post_keep is not None and key not in lv.post_keep:
                    continue
                if not lv.keeps(key):
                    continue
            elif lv.kind == "range":
                key, label, _ = _small_key(lv, k, index_name)
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
    return rows(level_i, agg, parent_count)


def format_levels(levels: List[Level], measures: List[Measure], agg_root: dict,
                  total_count: int, index_name: str) -> Tuple[List[dict], Dict[int, List[dict]]]:
    """Rows for every level, unnamed (`name_rows` names the ones that are returned),
    and each inner split's groups on their own over the whole set (for the summary)."""
    out = level_rows(levels, measures, 0, agg_root["s0"], total_count, index_name)
    margins = {lv.index: level_rows(levels, measures, lv.index, agg_root[f"m{lv.index}"], total_count, index_name)
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


def _vocab_table(column_id: str, entity: str) -> Optional[dict]:
    """A column's closed vocabulary, code -> name (countries, languages, types ...), or None."""
    try:
        from query_translation.oql_lang import entity_type_for_column
        from query_translation.oql_renderer import _config_table
        from query_translation.validator import CLOSED_VOCAB_NAMESPACE
        ns = CLOSED_VOCAB_NAMESPACE.get(entity_type_for_column(column_id, entity) or "")
        return (_config_table(ns) or None) if ns else None
    except Exception:  # noqa: BLE001 (no vocabulary table)
        return None


def _code_name(code: str, column_id: str, entity: str) -> str:
    """A closed vocabulary's code as its name (`US` -> "United States"); else the code."""
    table = _vocab_table(column_id, entity)
    return (table.get(code.lower()) if table else None) or code


def _name_vocab(column_id: str, entity: str) -> Optional[dict]:
    """A split of codes (`ZA`, `af`) whose key order the words call alphabetical
    (`, alphabetical by country`): its vocabulary, so its groups sort by name and the words
    stay true (#1658: by code, United Arab Emirates came before Albania). None for years,
    IDs (`in institution ID order`) and open text, which keep key order."""
    from query_translation.oql_core import key_order_is_alphabetical
    return _vocab_table(column_id, entity) if key_order_is_alphabetical(column_id) else None


def _order_value(v):
    """A cell as a sort key: numbers (and number-like keys, `"2026"`) before text, so a
    column never compares a number with a string."""
    if isinstance(v, (int, float)):        # bool too
        return (0, v, "")
    s = str(v)
    try:
        return (0, float(s), "")
    except ValueError:
        return (1, 0, s.lower())


def _sort_rows(rows: List[dict], sort: Optional[Tuple[str, str]], lv: Optional["Level"] = None):
    """Rows by one column, either way; groups with no value last. Ties keep the order
    they came in (the default: most works first), since Python's sort is stable. A key
    sort on a split of codes goes by the names the rows will show (`_name_vocab`)."""
    if not sort:
        return rows
    key, direction = sort
    value = lambda r: r.get(key)   # noqa: E731
    if key == "key" and lv is not None and lv.name_vocab is not None:
        names = _display_names(lv, [r["_raw"][1] for r in rows if "_raw" in r], None)
        value = lambda r: names.get(r["_raw"][1]) if "_raw" in r else None   # noqa: E731
    present = [r for r in rows if value(r) is not None]
    missing = [r for r in rows if value(r) is None]
    present.sort(key=lambda r: _order_value(value(r)), reverse=(direction == "desc"))
    return present + missing


def _is_year_level(lv: "Level") -> bool:
    """A split by publication year: its groups read oldest first unless a sort says
    otherwise (Jason's default, oxjob #1555 D4), like a chart's x-axis."""
    return lv.kind == "terms" and (lv.column_id or "").split(".")[-1] == "publication_year"


def _default_order(lv: "Level", rows: List[dict]) -> List[dict]:
    """A level's rows in its default order: years oldest first; everything else as ES
    returned them (most works first) or as listed."""
    if _is_year_level(lv):
        return sorted(rows, key=lambda r: _order_value(r.get("key")))
    return rows


def _order_levels(levels: List["Level"], rows: List[dict], sort: Optional[Tuple[str, str]],
                  level_i: int = 0, small_only: bool = False) -> List[dict]:
    """Every level of a nested table in the asked order (oxjob #1555 D4): a sort on the
    key orders the outer split's groups (inner groups keep their default); a sort on a
    number orders the groups at every level by it; no sort, each level's default.
    `small_only`: only the small splits' rows (a page view past the limits read its
    column splits in this order already, oxjob #1598)."""
    lv = levels[level_i]
    if small_only and not _small(lv):
        pass
    elif sort is None or (sort[0] == "key" and level_i > 0):
        rows = _default_order(lv, rows)
    else:
        rows = _sort_rows(rows, sort, lv)
    for r in rows:
        if r.get("groups") and level_i + 1 < len(levels):
            r["groups"] = _order_levels(levels, r["groups"], sort, level_i + 1, small_only)
    return rows


def _terms_after(index, connection, field: str, after, size: int, deadline: Deadline,
                 key_kind: str = "keyword") -> Optional[Tuple[List[str], bool]]:
    """The next `size` keys of a keyword field after `after` (exclusive), in key order, from the field's term list
    (Elasticsearch terms-enum: no works read; index-wide, so it also lists keys the set doesn't hold). Returns
    (keys, complete); None when the field can't list its keys or the call fails. Terms-enum lists keyword fields
    only: on a number or date field it answers an empty list, which is not "no keys left" (oxjob #1598)."""
    from elasticsearch_dsl.connections import get_connection
    if key_kind != "keyword":
        return None
    params = {"field": field, "size": size, "timeout": "2s"}
    if after is not None:
        params["search_after"] = after
    timeout = deadline.timeout("listing the next keys")
    try:
        res = get_connection(connection).terms_enum(index=index, request_timeout=timeout, **params)
    except Exception:
        return None
    terms = res.get("terms") or []
    complete = bool(res.get("complete", True))
    if not all(isinstance(t, str) for t in terms) or not (terms or complete):
        return None   # an empty, cut-short listing says nothing about what's left
    return terms, complete


def _keys_after(keys: List[str], after, size: int) -> List[str]:
    """The next `size` keys of a sorted key set after `after` (exclusive): a split filtered to a key set pages
    through its own keys, as `_terms_after` lists an unfiltered field's."""
    i = bisect_right(keys, after) if after is not None else 0
    return keys[i:i + size]


def _cursor_page(lv: Level, body: dict, index_name: str, connection, deadline: Deadline,
                 per_page: int, pref: str, past: Optional[Dict[str, Any]] = None,
                 keysets: Optional[Dict[str, Level]] = None) -> dict:
    """One cursor page of a composite (#1550), read range by range over a big set (oxjob #1598). Returns a search
    response shaped like the one request's: hits and the whole-set aggregations, with `s0` holding the page and an
    `after_key` exactly when groups remain (`exact_after`).

    A group's numbers come from the works that hold its key, so a query that keeps every work holding a key in
    (lo, hi] gives every group in that range exactly; the other keys those works hold (co-authors) come after hi in
    key order and are dropped. hi is the K-th key after lo in the field's term list. A small set (or a field that
    can't list its keys) is one range with no bounds, read as one request read it. The whole-set row and the group
    count are the same on every page, so after the first page Elasticsearch's request cache answers them.
    A page can come back short, even empty (it stops reading when PARTITION_RESERVE_S is left of the deadline, as a
    count filter keeps few of the keys it reads); its cursor is the last key read, exclusive, like every page's.

    Nested splits (a composite with one source per split) range on the leading split. Their cursor is the whole
    after-key, and "read through lead key k" is the after-key {lead: k, every other source: `past` it, a value above
    every key}, so the next range never sees a combination whose leading key it already read.

    `keysets` (source name -> its Level): splits filtered on their groups' own records (`by journal`, `by
    institution in [Canada](CA)`, `where last known institution is not ...`). A composite can't filter its keys, so
    the rows outside a key set are dropped as they are read; a leading split with an include list pages through its
    own sorted keys (KEYSET_CHUNK at a time, as a terms filter) instead of the index-wide term list, so it reads only
    the works holding its keys (oxjob #1598). The leading split's own fields pushed down to the works (`by
    journal`) narrow the works its groups are read from, not the whole-set row."""
    s0 = body["aggs"]["s0"]
    comp = {k: v for k, v in s0["composite"].items() if k != "after"}
    names = [next(iter(src)) for src in comp["sources"]]
    lead = names[0]
    nested = len(names) > 1
    start_after = s0["composite"].get("after")
    after = (start_after or {}).get(lead)
    field = comp["sources"][0][lead]["terms"]["field"]
    keysets = {n: k for n, k in (keysets or {}).items() if k.include is not None or k.exclude}
    # a count filter or a key set keeps few of the groups it reads
    filtered = "having" in (s0.get("aggs") or {}) or bool(keysets)
    walk = keysets[lead].kept_keys() if lead in keysets else None

    def keep(b) -> bool:
        return all(k.keeps(b["key"][n]) for n, k in keysets.items())

    def next_keys(pos, n: int) -> Optional[Tuple[List[str], bool]]:
        """The leading split's next keys after pos, and whether more may follow them (None: it can't list them):
        its key set's own keys, else the field's term list."""
        if walk is not None:
            keys = _keys_after(walk, pos, n)
            return keys, bool(keys) and keys[-1] != walk[-1]
        listed = _terms_after(index_name, connection, field, pos, n, deadline, lv.key_kind)
        return None if listed is None else (listed[0], len(listed[0]) >= n or not listed[1])

    def through(k) -> dict:
        return {lead: k, **(past or {})}

    whole = _search(index_name, connection,
                    {**body, "aggs": {k: v for k, v in body["aggs"].items() if k != "s0"}},
                    deadline, "calculating the whole set", preference=pref)
    aggs = dict(whole.get("aggregations") or {})
    took = whole.get("took") or 0
    n_groups = _groups_count(lv, aggs)
    ranged = walk is not None or (whole["hits"]["total"]["value"] >= PARTITION_MIN_WORKS
                                  and not (n_groups is not None and n_groups * 2 < per_page))
    # a leading key holds many combinations (an institution's authors), so nested ranges start small and grow
    # from what each one holds
    min_terms = min(PARTITION_MIN_TERMS, NESTED_MIN_TERMS) if nested else PARTITION_MIN_TERMS
    max_terms = KEYSET_CHUNK if walk is not None else PARTITION_MAX_TERMS

    def clamp(n: float) -> int:
        return int(min(max_terms, max(min_terms, n)))

    kept: List[dict] = []

    def page(next_after: Optional[dict]) -> dict:
        out = {"buckets": kept[:per_page], "exact_after": True}
        if next_after is not None:
            out["after_key"] = next_after
        aggs["s0"] = out
        return {"hits": whole["hits"], "took": took, "aggregations": aggs}

    pos, n_terms = after, clamp(min_terms if nested else 2 * per_page)
    first = True
    # a nested cursor that stopped inside a leading key (one institution's 30,000 authors fill several pages)
    # reads the rest of that key alone first, not a range of keys around it
    inside = pos is not None and start_after != through(pos)
    while True:
        if (kept or pos != after) and deadline.remaining() < PARTITION_RESERVE_S:
            return page(through(pos))   # a short (even empty) page; its cursor has moved on
        terms, hi, more = None, None, True
        if ranged and first and inside:
            terms, hi = [pos], pos
        elif ranged:
            listed = next_keys(pos, n_terms)
            if listed is None:
                ranged = False        # the field can't list its keys: the rest is one range
            else:
                terms, more = listed
                if not terms:
                    return page(None)  # no keys after pos anywhere
                # a key set's last range still stops at its last key (the co-keys after it read nothing it keeps)
                if more or walk is not None:
                    hi = terms[-1]
        # the rest of a leading key the cursor stopped inside: the composite's own after-key skips what was read
        low = "gte" if first and inside else "gt"
        rng = {**({low: pos} if pos is not None else {}), **({"lte": hi} if hi is not None else {})}
        if terms is not None and walk is not None:
            # the works holding these keys of the key set, not every key in their range
            query = _and(body["query"], {"terms": {field: terms}}, *lv.works_filters)
        elif terms is not None and rng:
            query = _and(body["query"], {"range": {field: rng}}, *lv.works_filters)
        else:
            query = _and(body["query"], *lv.works_filters) if lv.works_filters else body["query"]
        start = len(kept)
        cur = start_after if first else (through(pos) if pos is not None else None)
        first = False
        while True:
            # a count filter keeps few of the groups it reads: read a full page each time (one request per
            # range, sized to the range, measured slower: 65,535 groups 3.7 s vs 10,000 in 0.4 s)
            size = per_page if filtered else per_page - len(kept)
            c = {**comp, "size": size, **({"after": cur} if cur is not None else {})}
            res = _search(index_name, connection, {"size": 0, "query": query, "aggs": {"s0": {**s0, "composite": c}}},
                          deadline, "calculating the groups", preference=pref)
            took += res.get("took") or 0
            raw = res["aggregations"]["s0"]
            kept.extend(b for b in raw["buckets"] if (hi is None or b["key"][lead] <= hi) and keep(b))
            last = raw.get("after_key")
            # the range is read once the composite is past every combination of hi (a co-key after it; for one
            # split, hi itself); a nested page that ends on hi may have more of hi's combinations to read
            read = (last is None or (hi is not None and (last[lead] > hi or last == through(hi)))
                    or (not filtered and len(raw["buckets"]) < size))   # no keys left in the range
            if len(kept) > per_page:
                return page(kept[per_page - 1]["key"])
            if read:
                break
            cur = last                # more keys may be left in the range
            if len(kept) == per_page or deadline.remaining() < PARTITION_RESERVE_S:
                return page(cur)
        if hi is None or not more:
            return page(None)
        if len(kept) == per_page:
            return page(through(hi))
        pos = hi
        # size the next range from what this one held (index-wide keys the set lacks read nothing)
        n_terms = clamp((per_page - len(kept)) / (max(len(kept) - start, 1) / max(len(terms), 1)) * 1.2)


# ---------------------------------------------------------------------------
# Nested splits past the limits (oxjob #1598): the page shows the first rows, the cursor pages every combination
# ---------------------------------------------------------------------------
NESTED_FILL_BUCKETS = 60_000    # combinations one fill request may ask for (ES search.max_buckets is 65,536)
NESTED_MIN_TERMS = 50           # a nested cursor page's first range of leading keys
NESTED_3_MAX_ROWS = 200         # three splits: a page view up to this many rows (each level sized to the rows)
# The one-call summary export of a nested split past the limits lists each split's biggest groups, up to this many
# (naming 10,000 institutions and 10,000 authors took 6 s of a 13.8 s call, 2026-10-27); `split=<n>` with a cursor
# pages every group of a split (the exporter does, for each split cut here: `split_alone`).
NESTED_SUMMARY_GROUPS = 2_000
_PAST_EVERY_KEY = {"keyword": "\U0010ffff", "number": 2 ** 63 - 1, "date": 253402300799999}


def _small(lv: Level) -> bool:
    """A split with a fixed, short list of groups (listed values, searches, conditions, `at` bins, yes/no): each group
    is a query, so a nested split past the limits reads all of them for every key of its column splits."""
    return lv.kind in ("filters", "range")


# t = a split by a column, s = a small split
_SHAPES = {"tt": (0, 0), "ttt": (0, 0), "ts": (0, 1), "tts": (0, 1), "tss": (0, 2), "st": (1, 0), "stt": (1, 0)}


def _shape(levels: List[Level]) -> Optional[Tuple[int, int]]:
    """How a nested split pages: (small splits before its column splits, small splits after them), or None when it
    can't. The column splits page in a composite (key order); small splits after them ride under each combination
    (every group, as in one answer); one small split before them is walked a group at a time (oxjob #1598)."""
    return _SHAPES.get("".join("t" if lv.kind == "terms" else "s" if _small(lv) else "x" for lv in levels))


def _group_queries(lv: Level) -> List[Tuple[str, dict]]:
    """A small split's groups in their listed order, each as (bucket key, the query that keeps its works)."""
    if lv.kind == "filters":
        f = lv.agg["filters"]["filters"]
        return [(k, f[k]) for k in (lv.order_keys or list(f))]
    field = lv.agg["range"]["field"]
    return [(r["key"], {"range": {field: {**({"gte": r["from"]} if "from" in r else {}),
                                          **({"lt": r["to"]} if "to" in r else {})}}})
            for r in lv.agg["range"]["ranges"]]


def _small_agg(lv: Level, m_aggs: Dict[str, dict], inner: Optional[dict] = None) -> dict:
    """A small split's own aggregation (every group, in its order) with the measures and the next level under it."""
    sub = {**m_aggs, **(inner or {})}
    return {**lv.agg, "aggs": sub} if sub else dict(lv.agg)


def _level_groups(lv: Level, cards: Optional[Dict[int, int]]) -> Optional[int]:
    """A split's groups over the set: the probe's count for a column (approximate past 3,000), the list's length
    for a small split."""
    return len(lv.order_keys) if _small(lv) else (cards or {}).get(lv.index)


def _nested_pages_ok(levels: List[Level], measures: List[Measure], sort, cursor) -> bool:
    """Can this nested split page past the limits? Two or three splits by a column, or one or two of them with small
    splits (listed values, conditions, `at` bins, yes/no) after them, or one before them (`_shape`); group filters on
    the splits by a column: their groups' own records (a key set, `by institution in [Canada](CA)`, on any of them;
    pushed down to the works, `by journal`, on the leading one), a count floor only on the innermost; on a cursor page no share of the parent group (its count isn't
    read) and no sort; on the page, the default order, by count or by the outer key. Anything else keeps today's
    refusal."""
    if _shape(levels) is None:
        return False
    for lv in levels:
        if lv.post_keep is not None or lv.all_groups or "format" in lv.agg.get("terms", {}) \
                or (lv.works_filters and lv.index != 0):
            return False
        if lv.split.where is None:
            continue
        if lv.kind != "terms":
            return False
        m_parts = _split_where(lv.split.where)[0]
        # a calculation filter only as a count floor on the innermost split (min_doc_count, under the composite)
        if m_parts and (lv is not levels[-1] or not all(_is_count_floor(p) for p in m_parts)):
            return False
    if cursor is not None:
        # cursor pages go in key order (a sort orders the one answer within the limits)
        return not any(m.measure == "percent_of_those" for m in measures)
    if sort is not None:
        key = sort[0]
        if key not in ("count", "key") or (key == "key" and levels[0].name_vocab is not None):
            return False
    return True


def _pages_instead(e: AnalyticsError, levels: List[Level], measures: List[Measure], sort, cursor) -> bool:
    """A "too big for one answer" refusal that this nested split pages past instead."""
    return e.too_big and _nested_pages_ok(levels, measures, sort, cursor)


def _level_order(lv: Level, sort) -> List[dict]:
    """A level's terms order on the page, as `_order_levels` would sort a whole answer: a sort by count orders
    every level; a sort by key the outer level; else years oldest first, everything else most works first."""
    if sort and sort[0] == "count":
        return [{"_count": sort[1]}, {"_key": "asc"}]
    if sort and sort[0] == "key" and lv.index == 0:
        return [{"_key": sort[1]}]
    if _is_year_level(lv):
        return [{"_key": "asc"}]
    return [{"_count": "desc"}, {"_key": "asc"}]


def _level_terms(lv: Level, size: int, sort, m_aggs: Dict[str, dict], inner: Optional[dict] = None,
                 few_works: bool = False, include: Optional[List] = None) -> dict:
    """One level's terms aggregation for the page view: `size` groups in the page's order, its measures, a count
    floor (min_doc_count, applied before sizing, so the first groups by count are exact) and the next level.
    `few_works`: the request reads a few outer groups' works, where the map hint skips building the field's global
    ordinals (CNRS's 129K works of 2023 by author: 0.9 s with it, 4.8 s without, 2026-10-27). `include`: these keys
    only (a fill batch, already inside the split's key set), else the split's key set."""
    field = lv.agg["terms"]["field"]
    t = {"field": field, "size": size, "shard_size": max(size * 2, 3000), "order": _level_order(lv, sort)}
    if field in _MAP_HINT_FIELDS or few_works:
        t["execution_hint"] = "map"
    if lv.selector is not None:
        t["min_doc_count"] = _min_doc_count(lv.split.where)
    t.update({"include": include} if include is not None else _keyset_terms(lv))
    sub = {**m_aggs, **(inner or {})}
    return {"terms": t, "aggs": sub} if sub else {"terms": t}


def _leaf_slice(rows: List[dict], n: int, start: int, stop: int, depth: int = 0, seen: Optional[list] = None
                ) -> List[dict]:
    """The rows holding leaves start..stop-1 (in order) of a nested table, outer rows kept around them."""
    seen = [0] if seen is None else seen
    out = []
    for r in rows:
        if seen[0] >= stop:
            break
        if depth + 1 >= n:
            if seen[0] >= start:
                out.append(r)
            seen[0] += 1
            continue
        kids = _leaf_slice(r.get("groups") or [], n, start, stop, depth + 1, seen)
        if kids:
            out.append({**r, "groups": kids})
    return out


def _nested_cursor_rows(levels: List[Level], measures: List[Measure], buckets: List[dict], names: List[str],
                        index_name: str, first: int = 0) -> List[dict]:
    """Composite buckets (key order) back into the nested shape: outer rows carry their key and name, their own
    numbers aren't read on a cursor page; each combination is a leaf with its numbers. `names[j]` keys level
    `first + j`; small splits after the column splits come under each combination from its own aggregation (every
    group, as in one answer)."""
    cols = levels[first:first + len(names)]
    tail = first + len(names)
    rows: List[dict] = []
    for b in buckets:
        at = rows
        for j, lv in enumerate(cols):
            k = b["key"][names[j]]
            if j < len(cols) - 1 or tail < len(levels):
                if not (at and at[-1]["_raw"][1] == k):
                    at.append({"key": _row_key(k, lv, index_name), "key_display_name": None, "count": None,
                               "_raw": (lv.index, k), "groups": []})
                at = at[-1]["groups"]
                continue
            count = b["doc_count"]
            leaf = {"key": _row_key(k, lv, index_name), "key_display_name": None, "count": count, "_raw": (lv.index, k)}
            for m in measures:
                if m.measure != "count":
                    leaf[m.key] = _measure_value(m, b, count, None)
            at.append(leaf)
        if tail < len(levels):
            at.extend(level_rows(levels, measures, tail, b[f"s{tail}"], b["doc_count"], index_name))
    return rows


def _small_key(lv: Level, k: str, index_name: str) -> Tuple[str, Optional[str], Optional[str]]:
    """A small split's group `k` as (row key, name, raw key to name it by): a listed value is named later from its
    raw key (`name_rows`); a condition, bin or yes/no carries its name."""
    key, label = lv.labels[k]
    if lv.kind == "filters" and label is None:
        return _row_key(key, lv, index_name), None, key
    return key, label, None


def _small_row(lv: Level, k: str, index_name: str) -> dict:
    """A small split's group as an outer row on a cursor page (its numbers aren't read), keyed and named as
    `level_rows` keys it."""
    key, label, raw = _small_key(lv, k, index_name)
    return {"key": key, "key_display_name": label, "count": None, **({"_raw": (lv.index, raw)} if raw else {})}


def _whole_set_row(oqo: OQO, measures: List[Measure], aggs: dict, total_count: int) -> dict:
    """The summary's whole-set row: every measure over all the works (a share of them is always 100%, and a
    group's own field has no whole-set value)."""
    row = {"key": "all", "key_display_name": f"all {oqo.get_rows.replace('-', ' ')}", "count": total_count}
    for m in measures:
        if m.measure not in ("count", "value", "percent_of_those"):
            row[m.key] = _measure_value(m, aggs, total_count, None)
    return row


def _meta(oqo: OQO, measures: List[Measure], deadline: Deadline, *, count, took, page, per_page, groups_count,
          rows_count, more_groups, next_cursor) -> dict:
    """`groups_count`: the groups of the outer split (of the only split); `rows_count`: the table's rows, the
    rows an export writes (a nested split's combinations; None when not known, oxjob #1598)."""
    return {
        "count": count,
        "db_response_time_ms": took,
        "page": page,
        "per_page": per_page,
        "groups_count": groups_count,
        "rows_count": rows_count,
        "more_groups": more_groups,
        "next_cursor": next_cursor,
        "measures": [_measure_meta(m, oqo.get_rows) for m in measures],
        "splits": [split_meta(g, oqo.get_rows) for g in oqo.group_by],
        "es_calls": deadline.calls,
        "elapsed_ms": deadline.elapsed_ms(),
        "steps": deadline.log,
        "cost": price(oqo),
    }


def _nested_cursor(oqo: OQO, levels: List[Level], measures: List[Measure], m_aggs: Dict[str, dict],
                   having: Optional[dict], *, index_name: str, connection, base_query: dict, per_page: int,
                   deadline: Deadline, pref: str) -> Tuple[dict, List[dict], Optional[str]]:
    """One cursor page of every combination in key order: (a search response holding the whole set's numbers, the
    page's rows, next cursor). The column splits are one composite; small splits after them ride under each of its
    combinations (every group, so a page reads fewer combinations); a small split before them is walked one group
    at a time, the cursor saying which (`{"g": group, "a": the composite's after-key}`)."""
    from query_translation.analytics_csv import _leaves
    p, s = _shape(levels)
    cols = levels[p:len(levels) - s]
    names = [f"k{lv.index}" for lv in cols]
    under = None
    for lv in reversed(levels[len(levels) - s:]):
        under = {f"s{lv.index}": _small_agg(lv, m_aggs, under)}
    size = max(1, per_page // _cards_product(levels[len(levels) - s:], None))
    # a combination's own numbers are read only when it is the leaf
    sub = {**(under or m_aggs), **({"having": having} if having else {})}
    past = {n: _PAST_EVERY_KEY[lv.key_kind] for n, lv in zip(names[1:], cols[1:])}
    keysets = dict(zip(names, cols))

    def body(query: dict, after: Optional[dict], root: Dict[str, dict]) -> dict:
        comp = {"size": size, "sources": [{n: {"terms": {"field": lv.agg["terms"]["field"]}}}
                                          for n, lv in zip(names, cols)], **({"after": after} if after else {})}
        return {"size": 0, "track_total_hits": True, "query": query,
                "aggs": {**root, "s0": {"composite": comp, **({"aggs": sub} if sub else {})}}}

    def after_ok(a) -> bool:
        return isinstance(a, dict) and sorted(a) == sorted(names)

    if not p:
        after = None
        if oqo.cursor != "*":
            after = _decode_cursor(oqo.cursor)
            if not after_ok(after):
                raise _bad_cursor()
        res = _cursor_page(cols[0], body(base_query, after, m_aggs), index_name, connection, deadline, size, pref,
                           past=past, keysets=keysets)
        raw = res["aggregations"].get("s0") or {}
        rows = _nested_cursor_rows(levels, measures, raw.get("buckets") or [], names, index_name)
        return res, rows, (_encode_cursor(raw["after_key"]) if raw.get("after_key") else None)

    lead = levels[0]
    groups = _group_queries(lead)
    g, after = 0, None
    if oqo.cursor != "*":
        c = _decode_cursor(oqo.cursor)
        if not (isinstance(c, dict) and set(c) == {"g", "a"} and isinstance(c["g"], int)
                and 0 <= c["g"] < len(groups) and (c["a"] is None or after_ok(c["a"]))):
            raise _bad_cursor()
        g, after = c["g"], c["a"]
    # the whole set's numbers (the same on every page: the request cache answers them after the first)
    whole = _search(index_name, connection, {"size": 0, "track_total_hits": True, "query": base_query,
                                             **({"aggs": m_aggs} if m_aggs else {})},
                    deadline, "calculating the whole set", preference=pref)
    took = whole.get("took") or 0
    rows: List[dict] = []
    read, nxt = 0, None
    while True:
        k, q = groups[g]
        res = _cursor_page(cols[0], body(_and(base_query, q), after, {}), index_name,
                           connection, deadline, per_page - read, pref, past=past, keysets=keysets)
        took += res.get("took") or 0
        raw = res["aggregations"].get("s0") or {}
        got = _nested_cursor_rows(levels, measures, raw.get("buckets") or [], names, index_name, first=1)
        if got:
            rows.append({**_small_row(lead, k, index_name), "groups": got})
            read += sum(1 for _ in _leaves(got, 1, len(levels), []))
        if raw.get("after_key"):
            nxt = {"g": g, "a": raw["after_key"]}
            break
        g, after = g + 1, None
        if g == len(groups):
            break
        if read >= per_page or deadline.remaining() < PARTITION_RESERVE_S:
            nxt = {"g": g, "a": None}
            break
    return ({"hits": whole["hits"], "took": took, "aggregations": whole.get("aggregations") or {}}, rows,
            _encode_cursor(nxt) if nxt else None)


def _nested_first_rows(oqo: OQO, levels: List[Level], measures: List[Measure], m_aggs: Dict[str, dict], pool, *,
                       index_name: str, connection, base_query: dict, per_page: int, page: int, sort,
                       deadline: Deadline, pref: str, cards: Dict[int, int], summary_only: bool):
    """The first page x per_page rows in the usual order: the outer groups listed (one request; the combinations'
    estimate and, for the summary export, each inner split on its own run beside it), then each request reads a
    few outer groups' inner groups, sized to the rows still needed (per-group cardinality probes took 10.8-40.8 s,
    EXPLORE § 8); a small outer split (`_shape`) reads its groups one at a time. Returns (the listing's response, ES
    time in ms, the page's rows, the summary's splits, which of them hold only their biggest groups)."""
    from query_translation.analytics_csv import _leaves
    rows_wanted = page * per_page
    n = len(levels)
    p, _ = _shape(levels)
    lead = levels[0]
    if rows_wanted > MAX_PAGE_DEPTH or (n == 3 and rows_wanted > NESTED_3_MAX_ROWS):
        cap = MAX_PAGE_DEPTH if n == 2 else NESTED_3_MAX_ROWS
        raise AnalyticsError(
            "page_too_deep",
            f"Page {page} of {per_page} rows goes past the first {cap:,} rows of this table.",
            "Page through every row with cursor=* (in key order), or narrow the starting set.")
    # every row is in a different outer group at worst
    n_outer = min(rows_wanted, NESTED_SUMMARY_GROUPS) if summary_only else rows_wanted
    alone = None
    if summary_only:
        # each inner split on its own, for the summary export only: on the page it cost 2-5 s over a big set (all
        # works by author) and only priced the summary's own call, which charges its rows anyway
        alone = pool.submit(_search, index_name, connection, {"size": 0, "query": base_query, "aggs": {
            f"m{lv.index}": _small_agg(lv, m_aggs) if _small(lv) else _level_terms(lv, NESTED_SUMMARY_GROUPS, sort,
                                                                                   m_aggs)
            for lv in levels[1:]}}, deadline, "each split on its own", preference=pref)
    outer = _small_agg(lead, m_aggs) if p else _level_terms(lead, n_outer, sort, m_aggs)
    if lead.works_filters:
        # the outer groups over the works their pushed-down own fields keep; the whole-set row over every work
        outer = {"filter": _and(*lead.works_filters), "aggs": {"s0": outer}}
    listed = _search(index_name, connection, {"size": 0, "track_total_hits": True, "query": base_query, "aggs": {
        **m_aggs, "s0": outer}}, deadline, "listing the outer groups", preference=pref)
    total_count = listed["hits"]["total"]["value"]
    aggs = {**(listed.get("aggregations") or {}), **((alone.result().get("aggregations") or {}) if alone else {})}
    if lead.works_filters:
        aggs["s0"] = aggs["s0"]["s0"]
    outer_rows, margins = format_levels(levels, measures, aggs, total_count, index_name)
    margins[0] = [{k: v for k, v in r.items() if k != "groups"} for r in outer_rows]
    split_more = {lv.index: not summary_only or (not _small(lv) and (
        bool(aggs[f"m{lv.index}"].get("sum_other_doc_count"))
        or len(aggs[f"m{lv.index}"]["buckets"]) >= NESTED_SUMMARY_GROUPS)) for lv in levels[1:]}
    s0 = aggs.get("s0") or {}
    group_rows: List[dict] = []
    took = listed.get("took") or 0
    if p:
        split_more[0] = False
        if summary_only:
            return listed, took, group_rows, margins, split_more
        # one request per outer group, in the order a whole answer shows them, until the rows are read
        queries = dict(_group_queries(lead))
        key_of = {id(r): k for (k, _), r in zip(_bucket_rows(lead, s0), outer_rows)}
        need = rows_wanted
        for r in _order_levels(levels, outer_rows, sort, small_only=True):
            if need <= 0:
                break
            if not r["count"]:
                continue   # no works, no rows
            inner = None
            for lv in reversed(levels[1:]):
                inner = {f"s{lv.index}": _level_terms(lv, need, sort, m_aggs, inner)}
            res = _search(index_name, connection, {
                "size": 0, "query": _and(base_query, queries[key_of[id(r)]]), "aggs": inner},
                deadline, "reading the first groups", preference=pref)
            took += res.get("took") or 0
            r["groups"] = level_rows(levels, measures, 1, (res.get("aggregations") or {})["s1"], r["count"],
                                     index_name)
            group_rows.append(r)
            need -= sum(1 for _ in _leaves([r], 0, n, []))
        return listed, took, _leaf_slice(group_rows, n, (page - 1) * per_page, rows_wanted), margins, split_more
    outer_keys = [b["key"] for b in s0.get("buckets") or []]
    split_more[0] = bool(s0.get("sum_other_doc_count")) or len(outer_keys) >= n_outer
    if summary_only:
        return listed, took, group_rows, margins, split_more

    def per_outer(need: int) -> int:
        """Buckets one outer group's inner splits may hold."""
        b = 1
        for lv in levels[1:]:
            b *= len(lv.order_keys) if _small(lv) else need
        return b
    # the first batch: as many outer groups as the rows need if each held every inner group (a lower bound)
    need, i = rows_wanted, 0
    batch_n = max(1, -(-need // _cards_product(levels[1:], cards)))
    field0 = lead.agg["terms"]["field"]
    while need > 0 and i < len(outer_keys):
        batch_n = max(1, min(batch_n, NESTED_FILL_BUCKETS // max(per_outer(need), 1)))
        batch = outer_keys[i:i + batch_n]
        inner = None
        for lv in reversed(levels[1:]):
            inner = {f"s{lv.index}": _small_agg(lv, m_aggs, inner) if _small(lv)
                     else _level_terms(lv, need, sort, m_aggs, inner, few_works=True)}
        outer = _level_terms(lead, len(batch), sort, m_aggs, inner, few_works=True,
                             include=batch if all(isinstance(k, str) for k in batch) else None)
        res = _search(index_name, connection, {
            "size": 0, "query": _and(base_query, {"terms": {field0: batch}}, *lead.works_filters),
            "aggs": {"s0": outer}}, deadline, "reading the first groups", preference=pref)
        took += res.get("took") or 0
        filled, _ = format_levels(levels, measures, res.get("aggregations") or {}, total_count, index_name)
        by_key = {r["_raw"][1]: r for r in filled}
        for k in batch:
            if k in by_key and need > 0:
                group_rows.append(by_key[k])
                need -= sum(1 for _ in _leaves([by_key[k]], 0, n, []))
        i += len(batch)
        batch_n *= 4
    if any(_small(lv) for lv in levels):
        group_rows = _order_levels(levels, group_rows, sort, small_only=True)
    return listed, took, _leaf_slice(group_rows, n, (page - 1) * per_page, rows_wanted), margins, split_more


ESTIMATE_MAX_S = 6.0      # the combinations' estimate gets at most this long
ESTIMATE_RESERVE_S = 2.5  # and always leaves this much of the answer's deadline


class _Estimate:
    """The combinations' estimate, computed beside the page's own requests: None with a count floor (how many
    combinations pass it isn't known, as for one split), for the summary export (it doesn't use it), or when it
    can't finish in its own time (the sample over all works by author and year took 3.6-7.5 s on 2026-10-27; the
    exporter then charges each page as written, with no price up front)."""

    def __init__(self, pool, levels, index_name, connection, base_query, deadline, n_works, cards, known):
        self.known = known
        self.future = None
        if known is None and pool is not None:
            own = Deadline(min(ESTIMATE_MAX_S, deadline.remaining() - ESTIMATE_RESERVE_S))
            deadline.mark("estimating the combined groups")

            def count():
                try:
                    return _combined_groups(levels, index_name, connection, base_query, own, n_works, cards)
                except Exception:  # noqa: BLE001 (best effort: the page's rows stand without it)
                    return None
                finally:
                    deadline.calls += own.calls
            self.future = pool.submit(count)

    def value(self) -> Optional[int]:
        return self.future.result() if self.future is not None else self.known


def _nested_big(oqo: OQO, levels: List[Level], measures: List[Measure], m_aggs: Dict[str, dict], *,
                index_name: str, connection, base_query: dict, per_page: int, page: int, sort,
                deadline: Deadline, n_works: Optional[int], cards: Dict[int, int], groups: Optional[int],
                summary_only: bool = False) -> dict:
    """A nested split too big for one answer (oxjob #1598; Jason 2026-10-08: "No exceptions"). With a cursor:
    every combination in key order, a page at a time (a multi-source composite, ranged on the leading split like a
    single split's pages). Without one: the first page x per_page rows in the usual order, with `more_groups` and
    `groups_count` the estimated combinations."""
    from concurrent.futures import ThreadPoolExecutor
    # the same shards for every page of the query, so the whole-set row repeats from ES's request cache
    pref = clean_preference(json.dumps(replace(oqo, cursor=None).to_dict(), sort_keys=True))
    having = None
    if levels[-1].selector is not None:
        paths, script = levels[-1].selector
        having = {"bucket_selector": {"buckets_path": paths, "script": script}}
    margins: Dict[int, List[dict]] = {}
    with ThreadPoolExecutor(2) as pool:
        if oqo.cursor is not None:
            res, group_rows, next_cursor = _nested_cursor(
                oqo, levels, measures, m_aggs, having, index_name=index_name, connection=connection,
                base_query=base_query, per_page=per_page, deadline=deadline, pref=pref)
            estimate = _Estimate(None, levels, index_name, connection, base_query, deadline, n_works, cards,
                                 None if having else groups)
            took = res.get("took")
        else:
            known = groups if not (having or summary_only) else None
            estimate = _Estimate(None if (having or summary_only) else pool, levels, index_name, connection,
                                 base_query, deadline, n_works, cards, known)
            res, took, group_rows, margins, split_more = _nested_first_rows(
                oqo, levels, measures, m_aggs, pool, index_name=index_name, connection=connection,
                base_query=base_query, per_page=per_page, page=page, sort=sort, deadline=deadline, pref=pref,
                cards=cards, summary_only=summary_only)
            next_cursor = None
        total_count = res["hits"]["total"]["value"]
        aggs = res.get("aggregations") or {}
        deadline.mark("naming the groups")
        group_rows = name_rows(levels, group_rows, connection)
        margins = {i: name_rows(levels, rs, connection) for i, rs in margins.items()}
        fill_own_values(levels, group_rows, measures, deadline)
        for i, rs in margins.items():
            fill_own_values(levels, rs, measures, deadline, start_level=i)
        rows_count = estimate.value()
    summary = {"all": _whole_set_row(oqo, measures, aggs, total_count)}
    if oqo.cursor is None:
        # `groups_count`: the split's groups on their own (the probe's, approximate past 3,000; None past a count
        # floor, which the probe counts before), so the summary export can be priced before its splits are paged
        summary["splits"] = [{"groups": margins.get(lv.index, []), "more_groups": split_more[lv.index],
                              "groups_count": _level_groups(lv, cards) if lv.selector is None else None}
                             for lv in levels]
    # the outer split's groups, as within the limits: the run's probe (approximate past 3,000; a later cursor page
    # skips the probe)
    meta = _meta(oqo, measures, deadline, count=total_count, took=took, page=page, per_page=per_page,
                 groups_count=_level_groups(levels[0], cards), rows_count=rows_count,
                 more_groups=next_cursor is not None if oqo.cursor is not None else True, next_cursor=next_cursor)
    return {"meta": meta, "summary": summary, "group_by": group_rows, "results": []}


def run(oqo: OQO, *, index_name: str, connection, fields_dict, base_query: dict,
        per_page: Optional[int] = None, page: Optional[int] = None,
        sort: Optional[Tuple[str, str]] = None, deadline: Optional[Deadline] = None,
        summary_only: bool = False) -> dict:
    """Execute an analytics OQO. Returns the response body (without x_query). `summary_only`: the caller reads
    only the summary (a summary export), so a nested split past the limits skips reading its first rows."""
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
            if not _has_own_fields(lv.group_entity):
                raise AnalyticsError(
                    "group_filter_not_available",
                    f"A split by {_split_noun(lv)} can't filter on its groups' own records yet.",
                    f"Filter by a calculation, e.g. {count_fix(lv)}, or filter the starting works instead.")
            rest = resolve_keysets(lv, k_parts, oqo, index_name, connection, deadline,
                                   bool(m_parts), base_query=base_query,
                                   works_fields=fields_dict)
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
    # (a later nested cursor page goes straight to its page: it reads none of the probe's counts)
    n_works, cards = (_probe(levels, index_name, connection, base_query, deadline)
                      if (nested and any(lv.kind == "terms" for lv in levels)
                          and oqo.cursor in (None, "*")) else (None, {}))
    _cap_cards(cards, {lv.index: len(lv.kept_keys()) for lv in levels if lv.include is not None})

    # no sort asked: a single split by year reads oldest first (D4, oxjob #1555); the
    # OQO's sort_by stays empty, since a default isn't the user's choice
    eff_sort = sort
    if sort is None and len(levels) == 1 and _is_year_level(levels[0]):
        eff_sort = ("key", "asc")
    sort_m = next((x for x in measures if eff_sort and x.key == eff_sort[0]), None)
    by_own = sort_m is not None and sort_m.measure == "value"   # an own field orders the groups
    own_filled = False   # own fields already read for every group (to sort by one)
    sort_measure = None
    if eff_sort and not nested:
        key, direction = eff_sort
        m = sort_m
        by_name = key == "key" and bool(levels) and levels[0].name_vocab is not None
        if key == "count" or (m is not None and m.measure == "percent_of_those"):
            # a share of the whole set is the count over one number: the count's order
            sort_measure = {"_count": direction}
        elif m is not None and m.measure in ("mean", "sum", "min", "max", "median"):
            # groups with no value (a mean of nothing) sort last either way: first by
            # "has a value", then by the measure (ES put null means first on desc)
            path = f"m_{m.key}[50.0]" if m.measure == "median" else f"m_{m.key}"
            es_field = _es_number_field(fields_dict, m.column_id)
            m_aggs[f"h_{m.key}"] = {"max": {"script": {
                "source": f"doc['{es_field}'].size() > 0 ? 1 : 0"}}}
            sort_measure = [{f"h_{m.key}": "desc"}, {path: direction}]
        elif key == "key" and not by_name:
            sort_measure = {"_key": direction}
        elif ((by_name or (m is not None and m.measure in ("percent", "value"))) and levels
              and levels[0].kind == "terms" and levels[0].selector is None
              and levels[0].post_keep is None and oqo.cursor is None):
            # a percent, a group's own field, or codes by name (`alphabetical by country`):
            # ES can't order the split by it, so every group is read and sorted here (a
            # filtered split already reads them all)
            _read_all_groups(levels[0], m, cards, index_name, connection, base_query,
                             deadline, oqo.get_rows)
    cursor = oqo.cursor

    def big(e: AnalyticsError) -> dict:
        """A nested split too big for one answer pages instead, when it can (oxjob #1598); else the refusal."""
        if not _pages_instead(e, levels, measures, sort, cursor):
            raise e
        return _nested_big(oqo, levels, measures, m_aggs, index_name=index_name, connection=connection,
                           base_query=base_query, per_page=per_page, page=page, sort=sort, deadline=deadline,
                           n_works=n_works, cards=cards, groups=e.groups, summary_only=summary_only)

    # Everything that can refuse a nested split as too big for one answer (a split past 10,000 groups,
    # combinations past 65,536, an estimate past the deadline, too many buckets, a full count-filtered
    # level): `big` pages it instead when it can (oxjob #1598), else the refusal stands.
    try:
        if cursor is not None and nested:
            # nested splits page every combination in key order once they pass what one answer holds, small splits
            # (listed values, conditions, `at` bins, yes/no) beside the column ones too (oxjob #1598, `_shape`);
            # within the limits a cursor gets the one answer, with no next cursor
            if _shape(levels) is None:
                raise AnalyticsError(
                    "cursor_not_available",
                    "Cursor paging works on splits by a column, with listed values, conditions or bins after them "
                    "(or one before them).",
                    "Drop the cursor: the other shapes return all their groups at once.")
            if cursor != "*":
                raise AnalyticsError("cursor_not_available", "This cursor needs a query whose groups page.",
                                     "Start again with cursor=*.", too_big=True)
        elif cursor is not None:
            # one split pages through any number of groups, in key order (composite)
            if not levels or levels[0].kind != "terms":
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
                after = _decode_cursor(cursor)
                if isinstance(after, dict):
                    raise _bad_cursor()
                comp["after"] = {"k": after}
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
            groups = guard_nested(levels, cards, index_name, connection, base_query, deadline,
                                  n_works)
            if n_works is not None:
                est = estimate_main_seconds(n_works, groups or _cards_product(levels, cards))
                if est > QUERY_DEADLINE_S:
                    raise AnalyticsError(
                        "query_too_slow",
                        f"This query is estimated at {say_seconds(est)} ({n_works:,} works "
                        f"split {len(levels)} ways); queries get about "
                        f"{int(TIME_BUDGET_S)} seconds, so it wasn't run.",
                        "Narrow the starting set (a shorter year range, a smaller institution "
                        "or topic), split by something coarser, or drop a split.",
                        too_big=True, groups=groups)

        body = build_body(levels, base_query, m_aggs)
        if levels and not nested and levels[0].kind == "terms":
            lv0 = levels[0]
            field0 = (lv0.agg["composite"]["sources"][0]["k"]["terms"]["field"] if lv0.composite
                      else lv0.agg["terms"]["field"])
            if lv0.selector is None and lv0.post_keep is None and not lv0.all_groups:
                # how many groups a single split has in all (approximate past 3,000), less
                # what a key-set filter leaves out (all_groups counts its rows instead)
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
        pushed = levels[0].works_filters if levels else []
        if pushed:
            # the split and its group counts see only the works the pushed-down own fields
            # keep; the whole-set row (the root measures) still counts every work, and so do a
            # nested split's other splits on their own (m1, m2)
            # (a cursor page leaves the split itself on top: `_cursor_page` reads it from the pushed-down works)
            paged = not nested and levels[0].composite
            moved = {k: body["aggs"].pop(k) for k in list(body["aggs"])
                     if k not in m_aggs and (k == "s0" if nested else not (paged and k == "s0"))}
            body["aggs"]["pushed"] = {"filter": _and(*pushed), "aggs": moved}
        # same shards for the same query, so approximate counts repeat exactly
        pref = clean_preference(json.dumps(oqo.to_dict(), sort_keys=True))
        if levels and not nested and levels[0].composite:
            res = _cursor_page(levels[0], body, index_name, connection, deadline, per_page, pref,
                               keysets={"k": levels[0]})
        else:
            res = _search(index_name, connection, body, deadline, "calculating the groups",
                          preference=pref)
        total_count = res["hits"]["total"]["value"]
        aggs = res.get("aggregations", {})
        if pushed:
            lifted = aggs.pop("pushed")
            lifted.pop("doc_count")
            aggs.update(lifted)
        check_truncated(levels, aggs)
    except AnalyticsError as e:
        return big(e)

    all_row = _whole_set_row(oqo, measures, aggs, total_count)

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
            # every group of every level is here: order each level (D4, oxjob #1555)
            if by_own:
                fill_own_values(levels, group_rows, measures, deadline)
                for i, rs in margins.items():
                    fill_own_values(levels, rs, measures, deadline, start_level=i)
                own_filled = True
            group_rows = _order_levels(levels, group_rows, eff_sort)
            margins = {i: (_sort_rows(rs, eff_sort) if eff_sort and eff_sort[0] != "key"
                           else _default_order(levels[i], rs))
                       for i, rs in margins.items()}
            groups_count = len(group_rows)
        elif top.composite:
            raw = aggs["s0"]
            after = raw.get("after_key")
            # a cursor page says itself whether groups remain (#1598); one request can only tell by
            # coming back full
            if after and (raw.get("exact_after") or len(raw["buckets"]) >= per_page
                          or top.selector is not None):
                next_cursor = _encode_cursor(after["k"])
            more_groups = next_cursor is not None
            groups_count = _groups_count(top, aggs)
        elif top.kind == "terms" and top.all_groups:
            # every group came back (a sort ES can't do): sort them all, then page
            _check_all_groups(top, aggs, sort_m, oqo.get_rows)
            if by_own:
                fill_own_values(levels, group_rows, measures, deadline)
                own_filled = True
            group_rows = _sort_rows(group_rows, eff_sort, top)
            groups_count = len(group_rows)
            start = (page - 1) * per_page
            group_rows = group_rows[start:start + per_page]
            more_groups = start + per_page < groups_count
        elif top.kind == "terms" and not filtered:
            # one page of groups straight from ES, in its order
            if eff_sort and sort_measure is None:
                group_rows = _sort_rows(group_rows, eff_sort, top)
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
                    and eff_sort in (None, ("count", "desc"))):
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
            if by_own:
                if len(group_rows) > ALL_GROUPS_SORT_LIMIT:
                    raise _too_many_to_sort(top, sort_m, f"{len(group_rows):,}", oqo.get_rows)
                fill_own_values(levels, group_rows, measures, deadline)
                own_filled = True
            if eff_sort:
                group_rows = _sort_rows(group_rows, eff_sort, top)
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
    if not own_filled:
        if group_rows:
            fill_own_values(levels, group_rows, measures, deadline)   # the page only
        for i, rs in margins.items():
            fill_own_values(levels, rs, measures, deadline, start_level=i)
    summary = {"all": all_row}
    if nested:
        # each split's groups on their own, computed from the works (never summed
        # from group rows): the outer split is the top level of group_by
        summary["splits"] = [{"groups": [{k: v for k, v in r.items() if k != "groups"}
                                         for r in group_rows], "more_groups": False,
                              "groups_count": len(group_rows)}]
        for lv in levels[1:]:
            buckets = aggs.get(f"m{lv.index}", {}).get("buckets")
            # a terms split sized for the nested request came back full: more groups
            # exist over the whole set than the summary lists
            more = bool(lv.kind == "terms" and lv.size and isinstance(buckets, list)
                        and len(buckets) >= lv.size)
            summary["splits"].append({
                "groups": margins.get(lv.index, []), "more_groups": more,
                "groups_count": (cards.get(lv.index) if lv.selector is None else None) if more
                else len(margins.get(lv.index, []))})
    rows_count = groups_count
    if nested:
        # every combination is in a nested answer within the limits
        from query_translation.analytics_csv import _leaves
        rows_count = sum(1 for _ in _leaves(group_rows, 0, len(levels), []))
    meta = _meta(oqo, measures, deadline, count=total_count, took=res.get("took"),
                 page=page if levels else None, per_page=per_page if levels else None,
                 groups_count=groups_count, rows_count=rows_count if levels else None,
                 more_groups=more_groups, next_cursor=next_cursor)
    return {"meta": meta, "summary": summary, "group_by": group_rows, "results": []}


def _too_many_to_sort(lv: Level, m: Optional[Measure], how_many: str, entity: str = "works"):
    from query_translation.oql_pipeline import measure_text
    what = measure_text(m, entity.replace("-", " ")) if m is not None else "that column"
    return AnalyticsError(
        "too_many_groups",
        f"Sorting by {what} reads every {_split_noun(lv)} group, and there are "
        f"{how_many} here; a sort like this reads up to {ALL_GROUPS_SORT_LIMIT:,}.",
        f"Keep only the bigger groups with a count filter ({count_fix(lv, 100)}), or "
        f"narrow the starting set.")


def _read_all_groups(lv: Level, m: Measure, cards: Dict[int, int], index_name: str,
                     connection, base_query, deadline: Deadline, entity: str = "works"):
    """Size a single split to read every group, so a sort ES can't do (a percent, a
    group's own field) covers them all, not just the biggest (#524: a page of 8 by count
    put the Medical University of Vienna's 52.5% first, above smaller institutions at
    96.9%, and the answer changed with the page size)."""
    if lv.include is not None:
        # a key set (`by author at [UBC]`) caps the groups; ES says after the request
        # whether more than the limit came back
        cards[lv.index] = min(len(lv.kept_keys()), ALL_GROUPS_SORT_LIMIT)
    elif lv.name_vocab is not None:
        # a closed vocabulary caps the groups (247 countries): no cardinality probe
        cards[lv.index] = len(lv.name_vocab)
    else:
        # own fields pushed down to the works (#1617) narrow the groups too (`_probe`)
        card = _cardinalities([lv], index_name, connection, base_query, deadline)[lv.index]
        if card > ALL_GROUPS_SORT_LIMIT:
            raise _too_many_to_sort(lv, m, f"about {card:,}", entity)
        cards[lv.index] = card
    lv.all_groups = True


def _check_all_groups(lv: Level, aggs: dict, sort_m: Optional[Measure], entity: str):
    """An all-groups read came back whole, or the sort would cover only part of it."""
    raw = aggs.get("s0") or {}
    n = len(raw.get("buckets") or [])
    if raw.get("sum_other_doc_count") or n > ALL_GROUPS_SORT_LIMIT:
        raise _too_many_to_sort(lv, sort_m, f"more than {min(n, ALL_GROUPS_SORT_LIMIT):,}",
                                entity)


def _encode_cursor(key) -> str:
    import base64
    return "g1." + base64.urlsafe_b64encode(json.dumps(key).encode()).decode().rstrip("=")


def _bad_cursor() -> AnalyticsError:
    return AnalyticsError("invalid_cursor", "That cursor isn't one this query gave out.",
                          "Start again with cursor=*, then pass each next_cursor.")


def _decode_cursor(cursor: str):
    import base64
    try:
        if not cursor.startswith("g1."):
            raise ValueError
        raw = cursor[3:]
        return json.loads(base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4)))
    except Exception:
        raise _bad_cursor()


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
# One split by a column in count or key order reads a page of its groups, not all of them: its time follows the works
# (live 2026-10-29, oxjob #1598: all 330M works by author 7.7 s, works since 2020 by author 4.7 s and by source 2.0 s,
# since 2015 by institution with mean FWCI 3.5 s; the nested fit above read the first two as 9,180 s and 39 s)
EST_SINGLE_PAGE_FACTOR = 2.5


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
    """Splits by a column (terms; one, two or three of them) page through any number of
    groups with a cursor (nested ones once they pass what one answer holds, oxjob
    #1598); anything else (no split, listed values, searches, conditions, bins, yes/no)
    returns all its groups at once."""
    if not 1 <= len(oqo.group_by) <= 3:
        return False
    try:
        levels = [build_level(i, g, oqo, fields_dict, index_name) for i, g in enumerate(oqo.group_by)]
    except Exception:
        return False
    return levels[0].kind == "terms" if len(levels) == 1 else _shape(levels) is not None


def split_alone(oqo: OQO, n: int) -> OQO:
    """Split `n` (1-based) of a nested query on its own, over the whole set: the summary's by-<split> table (each
    split's groups computed from the works, its own group filter kept), as a single split, so it pages through any
    number of groups with a cursor like one (oxjob #1598, step 6)."""
    return replace(oqo, group_by=[oqo.group_by[n - 1]])


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
    own: Dict[int, int] = {}   # how many groups match a split's own-field filter (its key set's size, at most)
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
            pushed = _pushdown(lv, p, fields_dict)
            if pushed is not None:
                lv.works_filters.append(pushed)   # a works filter, as the run does it (`by journal`): no lookup
                continue
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
                n = _count_entity_matches(lv, p, deadline)
                if n is None:
                    continue
                own[lv.index] = min(n, own.get(lv.index, n))
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
    paged = False   # a nested split past one answer's limits that pages instead (oxjob #1598)
    one_page = False   # one split that reads a page of its groups
    measures = list(oqo.calculate) or [Measure("count")]
    sort = (oqo.sort_by[0].column_id, oqo.sort_by[0].direction or "desc") if oqo.sort_by else None
    try:
        n_works, cards = _probe(levels, index_name, connection, base_query, deadline)
        _cap_cards(cards, own)
        if nested:
            calls += 1                       # the run probes the splits too
            before = deadline.calls
            try:
                plan_levels(levels, cards, True, DEFAULT_PER_PAGE, 1, None)
                groups = guard_nested(levels, cards, index_name, connection, base_query,
                                      deadline, n_works)
                # as the run decides: past the deadline's estimate, it pages instead when it can
                if n_works is not None and estimate_main_seconds(
                        n_works, groups or _cards_product(levels, cards)) > QUERY_DEADLINE_S:
                    paged = _nested_pages_ok(levels, measures, sort, oqo.cursor)
            except AnalyticsError as e:
                if not _pages_instead(e, levels, measures, sort, oqo.cursor):
                    raise
                paged, groups = True, e.groups
            calls += deadline.calls - before
        elif levels:
            lv = levels[0]
            groups = cards.get(lv.index) if lv.kind == "terms" else max(len(lv.order_keys), 1)
            one_page = (lv.kind == "terms" and (sort is None or sort[0] in ("count", "key"))
                        and not (lv.split.where is not None and _split_where(lv.split.where)[0]))
    except AnalyticsError as e:
        limits.append(e.to_dict())
    if paged:
        # the first rows: the outer groups listed, then a request or two for their inner groups
        est += 2 * call_s
        calls += 2
    elif n_works is not None:
        if nested and groups is None:
            groups = _cards_product(levels, cards)   # count-filtered: all groups are counted
        main = (n_works / EST_WORKS_PER_S * EST_SINGLE_PAGE_FACTOR if one_page
                else estimate_main_seconds(n_works, groups or 1))
        est += max(0.0, main - EST_CALL_ID_SET_S)
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
        q = _translate(part, g_fields).to_dict()
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
