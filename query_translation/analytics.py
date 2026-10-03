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
                                `percent`, at every level and at the root (the total row)
    group filters on measures   min_doc_count + bucket_selector

Group filters on a group's own fields (an author's h-index), `co-author` and
`collaborator` need one lookup call first (measured in #1512: 2 calls, 3-6 s after a
count filter); their key sets become the terms `include` / `exclude`.

Every ES call gets the time left of the query's deadline (15 s, Jason 2026-10-03); a call
that runs out is abandoned (closing the connection cancels the search in ES) and the
query answers with a message saying how to narrow it.
"""
import json
import re
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from elasticsearch.exceptions import ConnectionTimeout, TransportError
from elasticsearch_dsl import Q, Search

import settings
from core.exceptions import APIQueryParamsError
from core.preference import clean_preference
from query_translation.oqo import (
    OQO, BranchFilter, GroupBy, LeafFilter, Measure, MeasureFilter)

# Limits (Jason, 2026-10-03; #1512 measured the costs).
QUERY_DEADLINE_S = 15.0        # the engine cancels anything still running
MAX_LEVEL_GROUPS = 10_000      # a nested split returns at most this many groups per split
MAX_RESPONSE_BUCKETS = 65_536  # ES search.max_buckets
FILTERED_CANDIDATES = 20_000   # a single split with a group filter checks this many groups
LOOKUP_LIMIT = 60_000          # own-field lookups list at most this many ids
DEFAULT_PER_PAGE = 200
MAX_PAGE_DEPTH = 10_000        # page x per_page on a single split
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


def too_slow(what: str) -> AnalyticsError:
    return AnalyticsError(
        "query_too_slow",
        f"This query ran past the {int(QUERY_DEADLINE_S)}-second limit while {what}, "
        f"so it was stopped.",
        "Narrow the starting set (a shorter year range, a smaller institution or topic), "
        "add a count filter before a filter on the groups' own fields "
        "(where count of those works > (10) and ...), or split it into several queries.")


# ---------------------------------------------------------------------------
# Measures
# ---------------------------------------------------------------------------
def _es_number_field(fields_dict, column_id: str) -> str:
    from core.utils import get_field
    f = get_field(fields_dict, column_id)
    return f.es_field()


def _true_query(fields_dict, column_id: str):
    """The field's own query for `true` (yes/no columns)."""
    import copy
    from core.utils import get_field
    f = copy.copy(get_field(fields_dict, column_id))
    f.value = "true"
    return f.build_query()


def _measure_aggs(measures: List[Measure], fields_dict) -> Dict[str, dict]:
    aggs = {}
    for m in measures:
        name = f"m_{m.key}"
        if m.measure in ("count", "percent_of_those"):
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
                    "instead: get works where ... is in (col_...); then group those works "
                    "by ...")
        filters = {}
        for j, v in enumerate(values):
            k = f"v{j}"
            filters[k] = _translate(LeafFilter(column_id, v), fields_dict).to_dict()
            lv.labels[k] = (_value_key(column_id, v), None)
            lv.order_keys.append(k)
        lv.agg = {"filters": {"filters": filters}}
        return lv
    if g.bins is not None:
        es_field = fld.es_field()
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


def resolve_keysets(lv: Level, parts: List, oqo: OQO, works_index: str, connection,
                    deadline: Deadline, has_measure_filter: bool) -> List:
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
            deferred.append(p)
            continue
        g_fields, _g_index = entity_index(lv.group_entity)
        q = _translate(p, g_fields)
        extra = [Q("range", works_count={"gt": 0})] if lv.group_entity == "authors" else []
        q_all = Q("bool", filter=[q] + extra) if extra else q
        ids = resolve_query_ids(lv.group_entity, q_all,
                                json.dumps(p.to_dict(), sort_keys=True), LOOKUP_LIMIT,
                                request_timeout=deadline.timeout("looking up the groups' own fields"))
        if ids is None:
            deferred.append(p)
            continue
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
    terms = [lv for lv in levels if lv.kind == "terms"]
    if not terms:
        return {}
    aggs = {f"card{lv.index}": {"cardinality": {"field": lv.agg["terms"]["field"],
                                                "precision_threshold": 3000}}
            for lv in terms}
    body = {"size": 0, "track_total_hits": True, "query": base_query, "aggs": aggs}
    res = _search(index, connection, body, deadline, "counting the groups")
    return {lv.index: res["aggregations"][f"card{lv.index}"]["value"] for lv in terms}


def _split_noun(lv: Level) -> str:
    from query_translation.oql_lang import _split_label
    return _split_label(lv.split)


def plan_levels(levels: List[Level], cards: Dict[int, int], nested: bool, per_page: int,
                page: int, sort_measure: Optional[str]):
    """Sizes and order for the terms splits; refuses what the group guard can't take."""
    for lv in levels:
        if lv.kind != "terms":
            continue
        card = cards.get(lv.index)
        terms = lv.agg["terms"]
        if nested:
            if card is not None and card > MAX_LEVEL_GROUPS:
                raise AnalyticsError(
                    "too_many_groups",
                    f"Splitting by {_split_noun(lv)} gives about {card:,} groups here; a "
                    f"nested split takes up to {MAX_LEVEL_GROUPS:,} groups per split.",
                    "Narrow the starting set, or make it the only split (one split pages "
                    "through any number of groups).")
            size = min(int((card or MAX_LEVEL_GROUPS) * 1.1) + 10, MAX_LEVEL_GROUPS)
        elif lv.selector is not None or lv.post_keep is not None or lv.split.where is not None:
            size = FILTERED_CANDIDATES
        else:
            size = page * per_page
            if size > MAX_PAGE_DEPTH:
                raise AnalyticsError(
                    "page_too_deep",
                    f"Page {page} of {per_page} groups goes past the first "
                    f"{MAX_PAGE_DEPTH:,} groups.",
                    "Sort the groups so the ones you want come first.")
        terms["size"] = size
        terms["shard_size"] = max(size * 2, 3000)
        lv.size = size
        order = [{"_count": "desc"}, {"_key": "asc"}]
        if sort_measure and not nested and lv.selector is None:
            order = [sort_measure, {"_key": "asc"}]
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
    measures at the root (the total row)."""
    inner: Dict[str, dict] = {}
    for lv in reversed(levels):
        sub = dict(measure_aggs)
        sub.update(inner)
        if lv.selector is not None:
            paths, script = lv.selector
            sub["having"] = {"bucket_selector": {"buckets_path": paths, "script": script}}
        body = dict(lv.agg)
        if sub:
            body["aggs"] = sub
        inner = {f"s{lv.index}": body}
    aggs = dict(measure_aggs)
    aggs.update(inner)
    return {"size": 0, "track_total_hits": True, "query": base_query, "aggs": aggs}


def _display_names(lv: Level, raw_keys: List, connection) -> Dict:
    """bucket key -> display name, the legacy group-by's way."""
    from elasticsearch_dsl import AttrDict
    from core.group_by.display_names import (
        get_display_name_mapping, get_key_display_name, requires_display_name_conversion)
    col = lv.column_id
    keys = [k for k in raw_keys if k not in (None, "unknown")]
    if not keys:
        return {}
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


def _bucket_rows(lv: Level, agg: dict) -> List[Tuple[str, dict]]:
    """(bucket key, bucket) in display order for one level's aggregation result."""
    buckets = agg["buckets"]
    if isinstance(buckets, dict):          # filters
        return [(k, buckets[k]) for k in lv.order_keys]
    if lv.kind == "range":
        return [(b["key"], b) for b in buckets]
    if lv.kind == "histogram":
        return [(b["key"], b) for b in buckets]
    return [(b.get("key_as_string", b["key"]) if isinstance(b["key"], (int, float)) and lv.column_id and
             "percentile" in lv.column_id else b["key"], b) for b in buckets]


def format_levels(levels: List[Level], measures: List[Measure], agg_root: dict,
                  total_count: int, index_name: str, connection) -> List[dict]:
    """Rows for every level, with names resolved once per level."""
    from core.group_by.results import format_key

    # pass 1: collect raw keys per terms/listed level for display names
    raw_by_level: Dict[int, set] = {lv.index: set() for lv in levels}

    def collect(level_i: int, agg: dict):
        lv = levels[level_i]
        for k, b in _bucket_rows(lv, agg):
            if lv.kind == "terms":
                raw_by_level[lv.index].add(k)
            elif lv.kind == "filters" and lv.labels.get(k, (None, None))[1] is None:
                raw_by_level[lv.index].add(lv.labels[k][0])
            nxt = f"s{level_i + 1}"
            if level_i + 1 < len(levels) and nxt in b:
                collect(level_i + 1, b[nxt])

    collect(0, agg_root["s0"])
    names = {lv.index: _display_names(lv, sorted(raw_by_level[lv.index], key=str), connection)
             for lv in levels if raw_by_level[lv.index]}

    def rows(level_i: int, agg: dict, parent_count: int) -> List[dict]:
        lv = levels[level_i]
        out = []
        for k, b in _bucket_rows(lv, agg):
            count = b["doc_count"]
            if lv.kind == "terms":
                if lv.post_keep is not None and k not in lv.post_keep:
                    continue
                if lv.column_id in ("authorships.author.id",) and not names.get(lv.index, {}).get(k):
                    continue  # merged/deleted author ids (the legacy group-by drops them too)
                key = format_key(k, lv.column_id, index_name) if isinstance(k, str) else str(k)
                if isinstance(k, (int, float)) and "openalex.org" not in str(k) and lv.column_id \
                        and lv.column_id.endswith(".id") and lv.group_entity:
                    key = f"{ID_PREFIX}{lv.group_entity}/{k}"
                label = names.get(lv.index, {}).get(k)
                label = str(k) if label is None else str(label)
            elif lv.kind == "filters":
                key, label = lv.labels[k]
                if label is None:
                    raw = key
                    key = format_key(raw, lv.column_id, index_name)
                    label = names.get(lv.index, {}).get(raw, raw)
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
                    label = f"{_num(lo)}-{_num(round(lo + w, 10))}"
                else:
                    hi = int(lo + w - 1)
                    label = _num(lo) if hi == int(lo) else f"{_num(lo)}-{hi}"
                key = label
            row = {"key": key, "key_display_name": label, "count": count}
            for m in measures:
                if m.measure != "count":
                    row[m.key] = _measure_value(m, b, count, parent_count)
            nxt = f"s{level_i + 1}"
            if level_i + 1 < len(levels) and nxt in b:
                row["groups"] = rows(level_i + 1, b[nxt], count)
            out.append(row)
        return out

    return rows(0, agg_root["s0"], total_count)


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
                    "Filter by a calculation, e.g. count of those works > (10).")
            rest = resolve_keysets(lv, k_parts, oqo, index_name, connection, deadline,
                                   bool(m_parts))
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
                        f"Add a count filter so only the busiest groups are looked up: "
                        f"where count of those works > (5) and ..., or narrow the starting set.")
                deferred[lv.index] = rest
                lv.post_keep = set()   # filled after the main request

    m_aggs = _measure_aggs(agg_measures, fields_dict)
    cards = _cardinalities(levels, index_name, connection, base_query, deadline) \
        if (nested and any(lv.kind == "terms" for lv in levels)) else {}

    sort_measure = None
    if sort and not nested:
        key, direction = sort
        m = next((x for x in measures if x.key == key), None)
        if key == "count":
            sort_measure = {"_count": direction}
        elif m is not None and m.measure in ("mean", "sum", "min", "max"):
            sort_measure = {f"m_{m.key}": direction}
        elif m is not None and m.measure == "median":
            sort_measure = {f"m_{m.key}[50.0]": direction}
        elif key == "key":
            sort_measure = {"_key": direction}
        # percent and percent_of_those sort after the fact (one page of groups)
    plan_levels(levels, cards, nested, per_page, page, sort_measure)

    body = build_body(levels, base_query, m_aggs)
    if (levels and not nested and levels[0].kind == "terms"
            and levels[0].split.where is None):
        # how many groups a single split has in all (approximate past 3,000)
        body["aggs"]["n_groups"] = {"cardinality": {"field": levels[0].agg["terms"]["field"],
                                                    "precision_threshold": 3000}}
    # same shards for the same query, so approximate counts repeat exactly
    pref = clean_preference(json.dumps(oqo.to_dict(), sort_keys=True))
    res = _search(index_name, connection, body, deadline, "calculating the groups",
                  preference=pref)
    total_count = res["hits"]["total"]["value"]
    aggs = res.get("aggregations", {})

    total_row = {"key": "total", "key_display_name": f"all {oqo.get_rows.replace('-', ' ')}",
                 "count": total_count}
    for m in measures:
        if m.measure != "count":
            total_row[m.key] = _measure_value(m, aggs, total_count, None)
    total_row.pop("percent_of_those", None)

    group_rows: List[dict] = []
    groups_count = None
    more_groups = False
    if levels:
        # survivors lookups (own fields checked only for groups that passed the rest)
        for idx, parts in deferred.items():
            lv = levels[idx]
            keys = sorted(_keys_at(levels, aggs, idx))
            lv.post_keep = survivors_lookup(lv, parts, keys, deadline)
        deadline.mark("naming the groups")
        group_rows = format_levels(levels, measures, aggs, total_count, index_name, connection)
        top = levels[0]
        filtered = (top.selector is not None or top.post_keep is not None
                    or top.split.where is not None)
        if nested:
            groups_count = len(group_rows)
        elif top.kind == "terms" and not filtered:
            # one page of groups straight from ES, in its order; a sort ES can't do
            # (percent) reorders that page
            if sort and sort_measure is None:
                group_rows = _sort_rows(group_rows, sort)
            start = (page - 1) * per_page
            group_rows = group_rows[start:start + per_page]
            more_groups = bool(aggs["s0"].get("sum_other_doc_count"))
            groups_count = (aggs.get("n_groups") or {}).get("value")
        else:
            # every group is here: sort and page in Python
            if sort:
                group_rows = _sort_rows(group_rows, sort)
            groups_count = len(group_rows)
            if top.kind == "terms":
                start = (page - 1) * per_page
                group_rows = group_rows[start:start + per_page]
                more_groups = start + per_page < groups_count

    meta = {
        "count": total_count,
        "db_response_time_ms": res.get("took"),
        "page": page if levels else None,
        "per_page": per_page if levels else None,
        "groups_count": groups_count,
        "more_groups": more_groups,
        "measures": [_measure_meta(m, oqo.get_rows) for m in measures],
        "es_calls": deadline.calls,
        "elapsed_ms": deadline.elapsed_ms(),
        "steps": deadline.log,
    }
    return {"meta": meta, "total": total_row, "group_by": group_rows, "results": []}


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
    return {k for k in out if isinstance(k, str)}


def _measure_meta(m: Measure, entity: str) -> dict:
    from query_translation.oql_pipeline import measure_text
    return {"key": m.key, "measure": m.measure, "column_id": m.column_id,
            "oql": measure_text(m, entity.replace("-", " "))}
