"""Running walks and sets (oxjob #1535, Rung 2 of #1512).

Walks and sets take a few Elasticsearch calls, run 8 at a time, inside the query's
time budget (about 10 s, cancelled at the deadline: analytics.Deadline). The rates
behind the estimates were measured on production (#1535 EXPLORE.md "Parallel
speedups"): with 8 calls in flight a walk handles about 36,000 things a second, and
listing a set's work ids runs at about 140,000 a second.

How each shape runs:

* a set defined by a whole query (`author is in (get works ...; then get authors of
  those works)`, `it cites works in (get works where ...)`) is resolved first into
  its ids, and the leaf becomes an `IdSet` filter (chunked `terms`);
* a walk to a combined set and back (`get authors of those works; then get all
  those authors' works`) becomes a works filter on the walked ids, so every split,
  calculation and list the works path has works on it unchanged;
* a walk to each thing and back (`get each author of those works; then get all
  that author's works; then, summarize using mean FWCI`) runs one aggregation per
  partition of about 25,000 things, 8 in flight, and names only the returned page;
* a walk out with nothing after it lists the things (Rung 1's split by them);
  `summarize using count` after a set walk counts them, exactly while that fits the
  budget, approximately (within 0.5%) past it, and says which.
"""
import math
from dataclasses import replace
from typing import Dict, List, Optional, Tuple

from elasticsearch_dsl import Q

from query_translation import analytics as A
from query_translation.id_split import INFLIGHT, PIECE_KEYS, _pmap, _terms, piece_full
from query_translation.oqo import (
    OQO, RELATION_COLUMNS, BranchFilter, GroupBy, LeafFilter, Measure, has_query_value,
    has_relation_leaf, result_entity)
from query_translation.walks import entity_for_link, link_for, plural, singular

PART_THINGS = 25_000         # things per aggregation call in a per-thing walk
LIST_PART = 50_000           # keys per listing call (under the 65,536-bucket cap)
MAX_SET_IDS = 450_000        # ids in one filter: about 16 MB of request, about 5 s
LISTED_MAX = 100             # each of up to this many things can be split further
EXACT_COUNT_MAX = 2_000_000  # distinct counts are exact up to this many (about 10 s)
EST_THINGS_PER_S = 36_000
EST_IDS_PER_S = 140_000
EST_FILTER_IDS_PER_S = 100_000
EST_OVERHEAD_S = 0.6


class IdSet:
    """A set resolved to its ids (full OpenAlex ids, or keys such as country codes),
    standing in for a whole query as a leaf's value while the query runs. `label`
    is the canonical text of the query it came from (what `to_dict` echoes)."""

    def __init__(self, ids: List[str], label: str, column: Optional[str] = None):
        self.ids = list(ids)
        self.label = label
        self.column = column    # the leaf's column as written (`cited_by`), for labels

    def __len__(self):
        return len(self.ids)

    def to_dict(self):
        return {"ids_of": self.label, "count": len(self.ids)}


def _split_trees(g: GroupBy) -> List:
    """The filter trees inside a split: its conditions, listed searches, group filter."""
    trees = list(g.conditions or [])
    trees += [v for v in (g.values or []) if isinstance(v, (LeafFilter, BranchFilter))]
    return trees


def needs_walk(oqo: OQO) -> bool:
    return (bool(oqo.walks) or oqo.each
            or any(has_query_value(f) or has_relation_leaf(f) for f in oqo.filter_rows)
            or any(has_query_value(t) for g in oqo.group_by for t in _split_trees(g)))


def _too_big(what: str, n: int, limit: int, fix: str) -> A.AnalyticsError:
    """`what` reads with the number: "uses a set of {n} works"."""
    return A.AnalyticsError("query_too_slow",
                            f"This query {what.format(n=f'about {n:,}')}; a set in "
                            f"parentheses holds up to {limit:,} to stay inside about "
                            f"{int(A.TIME_BUDGET_S)} seconds.", fix)


def _over_budget(seconds: float, what: str, fix: str):
    if seconds > A.TIME_BUDGET_S:
        raise A.AnalyticsError(
            "query_too_slow",
            f"This query {what}, estimated at {seconds:,.0f} seconds; queries get about "
            f"{int(A.TIME_BUDGET_S)}, so it wasn't run.", fix)


# ---------------------------------------------------------------------------
# Context: one per executed query
# ---------------------------------------------------------------------------
class Ctx:
    def __init__(self, connection, deadline: A.Deadline):
        from works.fields import fields_dict
        import settings
        self.connection = connection
        self.deadline = deadline
        self.works_fields = fields_dict
        self.works_index = settings.WORKS_INDEX

    def search(self, body, what, index=None, **params):
        return A._search(index or self.works_index, self.connection, body, self.deadline,
                         what, **params)

    def raw_field(self, column_id: str, fields_dict=None) -> str:
        """The exact-match ES field of a column (full ids, no lowercasing)."""
        from core.utils import get_field
        if column_id == "ids.openalex":
            return "id"
        fld = get_field(fields_dict or self.works_fields, column_id)
        return fld.alias if getattr(fld, "alias", None) else fld.es_sort_field()


# ---------------------------------------------------------------------------
# Building blocks
# ---------------------------------------------------------------------------
def _works_query(oqo: OQO, ctx: Ctx) -> dict:
    """The starting works of `oqo` (no walks) as one filter-context ES query."""
    from query_translation.execution import _base_query_for
    start = replace(oqo, walks=[], each=False, group_by=[], calculate=[], sort_by=[])
    return _base_query_for(start, ctx.works_fields, ctx.connection)


def _and(*queries) -> dict:
    qs = [q for q in queries if q]
    return {"bool": {"filter": qs}}


def count_distinct(ctx: Ctx, query: dict, field: str, what: str) -> int:
    r = ctx.search({"size": 0, "query": query, "aggs": {"n": {"cardinality": {
        "field": field, "precision_threshold": 40000}}}}, what)
    return int(r["aggregations"]["n"]["value"])


def list_keys(ctx: Ctx, query: dict, field: str, est: int, what: str,
              map_hint: bool = False) -> List:
    """Every distinct value of `field` in the works `query` matches, in hash
    partitions of about 50,000 listed side by side (each partition one call)."""
    parts = max(1, math.ceil(est * 1.15 / LIST_PART))

    def one(i):
        terms = {"field": field, "size": PIECE_KEYS,
                 "include": {"partition": i, "num_partitions": parts}}
        if map_hint:
            terms["execution_hint"] = "map"   # referenced_works: 10 s per call without it
        r = ctx.search({"size": 0, "query": query, "aggs": {"k": {"terms": terms}}}, what)
        agg = r["aggregations"]["k"]
        if piece_full(agg):
            raise A.AnalyticsError("query_too_slow",
                                   "A partition of this walk came back full; it can't be "
                                   "listed exactly.", "Narrow the starting set.")
        return [b["key"] for b in agg["buckets"]]
    out: List = []
    for keys in _pmap(one, range(parts)):
        out.extend(keys)
    return out


def list_work_ids(ctx: Ctx, query: dict, n: int, what: str) -> List[str]:
    """The ids of the works `query` matches: year partitions plus one for works with
    no year (else those go missing), each paged with search_after, side by side."""
    r = ctx.search({"size": 0, "query": query, "aggs": {"y": {"terms": {
        "field": "publication_year", "size": 500}}}}, what)
    years = sorted((b["key"], b["doc_count"]) for b in r["aggregations"]["y"]["buckets"])
    k = max(1, min(INFLIGHT, math.ceil(n / 20_000)))
    target, groups, cur, acc = n / k, [], [], 0
    for y, c in years:
        cur.append(y)
        acc += c
        if acc >= target and len(groups) < k - 1:
            groups.append((cur[0], cur[-1]))
            cur, acc = [], 0
    if cur:
        groups.append((cur[0], cur[-1]))
    parts = [_and(query, {"range": {"publication_year": {"gte": a, "lte": b}}})
             for a, b in groups]
    parts.append({"bool": {"filter": [query],
                           "must_not": [{"exists": {"field": "publication_year"}}]}})

    def page_all(q):
        after, ids = None, []
        while True:
            body = {"size": 10_000, "_source": False, "sort": [{"id": "asc"}], "query": q,
                    "track_total_hits": False}
            if after:
                body["search_after"] = after
            hits = ctx.search(body, what)["hits"]["hits"]
            ids.extend(h["_id"] for h in hits)
            if len(hits) < 10_000:
                return ids
            after = hits[-1]["sort"]
    out: List[str] = []
    for ids in _pmap(page_all, parts):
        out.extend(ids)
    return out


def _own_fields_query(entity: str, where) -> Tuple[dict, str]:
    """(ES filter on `entity`'s own index, its index) for a walk's `where`."""
    from core.join_resolver import entity_index
    from query_translation.oqo_to_es import _translate
    fields_dict, index = entity_index(entity)
    q = _translate(where, fields_dict)
    return (q.to_dict() if q is not None else {"match_all": {}}), index


def narrow(ctx: Ctx, entity: str, keys: List[str], where) -> List[str]:
    """The `keys` whose own record matches `where` (an author's h-index): id-filtered
    searches of 10,000, side by side."""
    q, index = _own_fields_query(entity, A._es_tree(where))
    chunks = [keys[i:i + 10_000] for i in range(0, len(keys), 10_000)]
    # `at [UBC](I141945490) since 2022`: the years are checked in each record (#1555)
    years = A._has_affiliation(where)

    def one(chunk):
        r = ctx.search({"size": len(chunk), "_source": ["id", "affiliations"] if years else ["id"],
                        "query": {"bool": {"filter": [{"terms": {"id": chunk}}, q]}}},
                       f"checking the {plural(entity)}' own fields", index=index)
        return [h["_source"]["id"] for h in r["hits"]["hits"]
                if not years or A._record_matches(where, h["_source"])]
    keep = set()
    for got in _pmap(one, chunks):
        keep.update(got)
    return [k for k in keys if k in keep]


def _entity_ids(ctx: Ctx, oqo: OQO) -> List[str]:
    """The ids of a non-works start (`get each institution in (I1, I2)`, `get authors
    where h-index > (50)`)."""
    from core.join_resolver import entity_index, list_short_ids
    from elasticsearch_dsl import Search
    from query_translation.execution import _base_query_for
    ids = _listed_ids(oqo)
    if ids is not None:
        return ids
    fields_dict, index = entity_index(oqo.get_rows)
    q = _base_query_for(replace(oqo, walks=[], each=False, group_by=[], calculate=[]),
                        fields_dict, ctx.connection)
    r = ctx.search({"size": 0, "track_total_hits": True, "query": q},
                   f"counting the {oqo.get_rows}", index=index)
    n = r["hits"]["total"]["value"]
    _over_budget(EST_OVERHEAD_S + n / 40_000 + n / EST_THINGS_PER_S,
                 f"starts from {n:,} {oqo.get_rows}",
                 f"Narrow the {oqo.get_rows} with more conditions.")
    base = Search(index=index, using=ctx.connection).filter(Q(q))
    short = list_short_ids(base, request_timeout=ctx.deadline.timeout(
        f"listing the {oqo.get_rows}"))
    return [A.ID_PREFIX + s for s in short]


def _listed_ids(oqo: OQO) -> Optional[List[str]]:
    """The ids written in `get each institution in (I1, I2)`, when that's the whole
    start (an OR of `ids.openalex` leaves); None otherwise."""
    if len(oqo.filter_rows) != 1:
        return None
    f = oqo.filter_rows[0]
    leaves = [f] if isinstance(f, LeafFilter) else (
        f.filters if isinstance(f, BranchFilter) and f.join == "or" else [])
    if not leaves or not all(isinstance(x, LeafFilter) and x.column_id == "ids.openalex"
                             and x.operator == "is" and not x.is_negated
                             and isinstance(x.value, str) for x in leaves):
        return None
    return [v if v.startswith(A.ID_PREFIX) else A.ID_PREFIX + v
            for v in (x.value for x in leaves)]


# ---------------------------------------------------------------------------
# Sets defined by a whole query
# ---------------------------------------------------------------------------
def resolve_sets(oqo: OQO, ctx: Ctx, walk_wheres: bool = True) -> OQO:
    """Replace every leaf whose value is a whole query, and every co-author or
    collaborator leaf, by its resolved ids."""
    def walk(node):
        if isinstance(node, BranchFilter):
            return replace(node, filters=[walk(f) for f in node.filters])
        if isinstance(node, LeafFilter) and isinstance(node.value, OQO):
            return _resolve_leaf(node, ctx)
        if isinstance(node, LeafFilter) and node.column_id in RELATION_COLUMNS:
            return _resolve_relation(node, ctx)
        return node
    walks = oqo.walks
    if walk_wheres:
        walks = [replace(w, where=walk(w.where)) if w.where is not None else w for w in walks]

    def split(g: GroupBy) -> GroupBy:
        # a set inside a split's condition (`into ((it cites works in (...)))`)
        if not any(has_query_value(t) for t in _split_trees(g)):
            return g
        conditions = [walk(c) for c in g.conditions] if g.conditions is not None else None
        values = ([walk(v) if isinstance(v, (LeafFilter, BranchFilter)) else v
                   for v in g.values] if g.values is not None else None)
        return replace(g, conditions=conditions, values=values)
    return replace(oqo, filter_rows=[walk(f) for f in oqo.filter_rows], walks=walks,
                   group_by=[split(g) for g in oqo.group_by])


def _resolve_relation(leaf: LeafFilter, ctx: Ctx) -> LeafFilter:
    """`co-author is (A1)`: the authors who share a work with A1 (and A1), as ids;
    `collaborator is (I1)`: the institutions on I1's works. Rung 1's group filters
    resolve the same words the same way (analytics._coauthor_keys)."""
    if leaf.column_id == "co_author":
        field, what = "authorships.author.id", "co-author"
    else:
        field, what = "authorships.institutions.lineage", "collaborator"
    keys = A._coauthor_keys(ctx.works_index, ctx.connection, [leaf.value], field, field,
                            ctx.deadline, what)
    return LeafFilter("ids.openalex", IdSet(sorted(keys), f"{what} of {leaf.value}"), "in",
                      leaf.is_negated)


def _resolve_leaf(leaf: LeafFilter, ctx: Ctx) -> LeafFilter:
    from query_translation.oql_pipeline import render_pipeline_line
    inner = leaf.value
    label = render_pipeline_line(inner)
    what = "listing the set in parentheses"
    if leaf.column_id == "cited_by":
        # works cited by the set's works: their references
        works_q = _set_works_query(inner, ctx)
        est = count_distinct(ctx, works_q, "referenced_works", what)
        if est > MAX_SET_IDS:
            raise _too_big("needs the {n} works the set in parentheses cites", est,
                           MAX_SET_IDS,
                           "Narrow the query in parentheses (a shorter year range, a "
                           "smaller institution or topic).")
        _over_budget(EST_OVERHEAD_S + est / EST_IDS_PER_S + est / EST_FILTER_IDS_PER_S,
                     f"reads the references of a set that cites about {est:,} works",
                     "Narrow the query in parentheses.")
        ids = list_keys(ctx, works_q, "referenced_works", est, what, map_hint=True)
        return LeafFilter("ids.openalex", IdSet(ids, label, "cited_by"), "in", leaf.is_negated)
    ids = resolve_result_ids(inner, ctx, what)
    column = leaf.column_id
    return LeafFilter(column, IdSet(ids, label, column), "in", leaf.is_negated)


def _set_works_query(inner: OQO, ctx: Ctx) -> dict:
    """The works a set query ends on, as an ES query (its walks resolved)."""
    if result_entity(inner) != "works":
        raise A.AnalyticsError("invalid_query_set",
                               "This relation takes a set of works.",
                               "End the query in parentheses at its works.")
    if not inner.walks:
        return _works_query(inner, ctx)
    kind, plan = plan_walk(inner, ctx)
    return plan["works_query"]


def resolve_result_ids(inner: OQO, ctx: Ctx, what: str) -> List:
    """The ids of what a set query returns: its works, or the things it walks to."""
    end = result_entity(inner)
    if end == "works":
        q = _set_works_query(inner, ctx)
        n = ctx.search({"size": 0, "track_total_hits": True, "query": q},
                       what)["hits"]["total"]["value"]
        if n > MAX_SET_IDS:
            raise _too_big("uses a set of {n} works", n, MAX_SET_IDS,
                           "Narrow the query in parentheses (a shorter year range, a "
                           "smaller institution or topic), or save the set as a "
                           "collection.")
        _over_budget(EST_OVERHEAD_S + n / EST_IDS_PER_S + n / EST_FILTER_IDS_PER_S,
                     f"uses a set of {n:,} works", "Narrow the query in parentheses.")
        return list_work_ids(ctx, q, n, what)
    if inner.get_rows == end and not inner.walks:
        return _entity_ids(ctx, inner)
    kind, plan = plan_walk(inner, ctx)
    return plan["keys"]


# ---------------------------------------------------------------------------
# Walks
# ---------------------------------------------------------------------------
def plan_walk(oqo: OQO, ctx: Ctx, need_keys: bool = True) -> Tuple[str, dict]:
    """Resolve the walked things. Returns (kind, plan): kind is "each" (one result per
    thing, then their works), "set" (their works as one set), "things" (the walk
    ends at the things) or "start" (a non-works start with no walk). `need_keys`
    False skips listing the things when the walk ends at them."""
    out = next((w for w in oqo.walks if w.to is None), None)
    back = next((w for w in oqo.walks if w.to is not None), None)
    if out is not None:
        link = out.column_id
        entity = entity_for_link(link)
        base = _works_query(oqo, ctx)
        field = ctx.raw_field(link)
        n = count_distinct(ctx, base, field, f"counting the {plural(entity)}")
        plan = {"link": link, "entity": entity, "base": base, "field": field, "n": n,
                "out": out, "back": back, "each": out.each}
        if back is None and (not need_keys or (not out.where and n > EXACT_COUNT_MAX)):
            return "things", plan
        if back is None and not out.where:
            plan["keys"] = list_keys(ctx, base, field, n, f"listing the {plural(entity)}")
            return "things", plan
        searched = any(A._tree_has_search(f) for f in oqo.filter_rows)
        est = (EST_OVERHEAD_S + n / EST_THINGS_PER_S
               + (math.ceil(n / LIST_PART / INFLIGHT) * A.EST_CALL_SEARCH_SET_S
                  if searched else 0))
        _over_budget(est, f"walks to about {n:,} {plural(entity)} (a walk handles about "
                          f"{EST_THINGS_PER_S:,} a second)",
                     f"Narrow the starting works (a shorter year range, a smaller "
                     f"institution or topic), or filter the {plural(entity)} as you walk "
                     f"to them (get each {singular(entity)} of those works where ...).")
        keys = list_keys(ctx, base, field, n, f"listing the {plural(entity)}")
        if out.where is not None:
            keys = narrow(ctx, entity, keys, out.where)
    elif oqo.get_rows != "works":
        entity = oqo.get_rows
        link = link_for(entity)
        keys = _entity_ids(ctx, oqo)
        plan = {"link": link, "entity": entity, "field": ctx.raw_field(link) if link else None,
                "n": len(keys), "out": None, "back": back, "each": oqo.each}
        if back is None:
            return "start", plan
    else:
        raise A.AnalyticsError("invalid_walk", "Nothing to walk.", "")
    plan["keys"] = sorted(keys, key=str)
    walked = [plan["keys"]] if plan["keys"] else [[]]
    back_q = None
    if back is not None and back.where is not None:
        from query_translation.oqo_to_es import _translate
        q = _translate(back.where, ctx.works_fields)
        back_q = q.to_dict() if q is not None else None
    plan["back_query"] = back_q
    core = _core_filter(oqo, ctx)
    plan["works_query"] = _and(core, _terms(plan["field"], plan["keys"]), back_q)
    if back is None:
        return "things", plan
    return ("each" if plan["each"] else "set"), plan


def _core_filter(oqo: OQO, ctx: Ctx) -> Optional[dict]:
    """The corpus filter the walked-back works carry (core works by default)."""
    from query_translation.execution import _effective_corpus
    corpus = _effective_corpus(replace(oqo, get_rows="works"), ctx.connection)
    if corpus is None:
        return None
    return {"term": {"is_xpac": "false" if corpus == "core" else "true"}}


def prepare(oqo: OQO, connection, deadline: A.Deadline) -> Tuple[str, object]:
    """Resolve an OQO's sets and walks. Returns ("oqo", an OQO the works path runs as
    is) or ("body", a finished response body)."""
    ctx = Ctx(connection, deadline)
    back = next((w for w in oqo.walks if w.to is not None), None)
    out = next((w for w in oqo.walks if w.to is None), None)
    if back is None and not oqo.calculate and out is not None:
        # the walk ends at the things: list them, each with its count in the set and
        # filtered by its own fields: Rung 1's split by them (its lookups, co-author
        # and collaborator filters included)
        start = replace(resolve_sets(oqo, ctx, walk_wheres=False), walks=[], each=False)
        return "oqo", replace(start, group_by=[GroupBy(column_id=out.column_id,
                                                       where=out.where)],
                              calculate=[Measure("count")])
    oqo = resolve_sets(oqo, ctx)
    if not oqo.walks and not oqo.each:
        return "oqo", oqo
    if not oqo.walks and oqo.each:
        return "oqo", replace(oqo, each=False)   # a list of the things themselves
    kind, plan = plan_walk(oqo, ctx)
    if kind == "set":
        # their works as one set: a works filter, then everything works can do
        works = OQO(get_rows="works", corpus=oqo.corpus,
                    filter_rows=[LeafFilter(plan["link"], IdSet(plan["keys"], "walked"), "in")]
                    + _flat(back.where),
                    group_by=oqo.group_by, calculate=oqo.calculate, sort_by=oqo.sort_by,
                    select=oqo.select, per_page=oqo.per_page, page=oqo.page,
                    cursor=oqo.cursor)
        return "oqo", works
    if kind == "each" and oqo.group_by and len(plan["keys"]) <= LISTED_MAX:
        # each of a few things, their works split further (MIT and Stanford by year):
        # Rung 1's split by listed values, then the query's own splits
        short = [k.replace(A.ID_PREFIX, "") if isinstance(k, str) else k
                 for k in plan["keys"]]
        works = OQO(get_rows="works", corpus=oqo.corpus,
                    filter_rows=[LeafFilter(plan["link"], IdSet(plan["keys"], "walked"), "in")]
                    + _flat(back.where),
                    group_by=[GroupBy(column_id=plan["link"], values=short)] + oqo.group_by,
                    calculate=oqo.calculate, sort_by=oqo.sort_by, per_page=oqo.per_page,
                    page=oqo.page)
        return "oqo", works
    if kind == "each":
        return "body", run_each(oqo, plan, ctx)
    if kind == "things":
        return "body", count_things(oqo, plan, ctx)
    return "oqo", replace(oqo, walks=[], each=False)


def _flat(tree) -> List:
    if tree is None:
        return []
    if isinstance(tree, BranchFilter) and tree.join == "and" and not tree.is_negated:
        return list(tree.filters)
    return [tree]


def count_things(oqo: OQO, plan: dict, ctx: Ctx) -> dict:
    """`get authors of those works; then, summarize using count`: how many distinct things.
    Exact while listing them fits the budget; else approximate (`cardinality`,
    within 0.5% on sets measured 2026-10-03), and the result says which."""
    entity = plan["entity"]
    if "keys" in plan:
        n, exact = len(plan["keys"]), True
    elif plan["n"] <= EXACT_COUNT_MAX:
        keys = list_keys(ctx, plan["base"], plan["field"], plan["n"],
                         f"counting the {plural(entity)}")
        n, exact = len(keys), True
    else:
        n, exact = plan["n"], False
    # the summary of the whole set (#1550's shape: `total` became `summary.all`)
    total = {"key": "all", "key_display_name": f"{plural(entity)} of those works",
             "count": n}
    meta = _meta(oqo, ctx, count=n, groups=None)
    meta["approximate"] = not exact
    return {"meta": meta, "summary": {"all": total}, "group_by": [], "results": []}


def run_each(oqo: OQO, plan: dict, ctx: Ctx) -> dict:
    """One result per walked thing over all its works: an aggregation per partition
    of about 25,000 things, 8 in flight; the total row is all their works together."""
    if oqo.group_by:
        raise A.AnalyticsError(
            "split_not_available",
            "Splitting each thing's works (each author's works by year) isn't available "
            "yet.",
            "Drop the split, or walk to the combined set: get authors of those works; "
            "then, get all those authors' works; then, group those works by year.")
    measures = list(oqo.calculate) or [Measure("count")]
    m_aggs = A._measure_aggs(measures, ctx.works_fields)
    keys, field = plan["keys"], plan["field"]
    core = _core_filter(oqo, ctx)
    # at least one partition per call slot, so a small walk uses all 8 too (31K KU
    # authors in 2 partitions of 25K took 6 s; a few prolific authors carry most works)
    size = max(1_000, min(PART_THINGS, math.ceil(len(keys) / INFLIGHT)))
    chunks = [keys[i:i + size] for i in range(0, len(keys), size)] or [[]]

    def part(chunk):
        if not chunk:
            return []
        body = {"size": 0, "query": _and(core, {"terms": {field: chunk}}, plan["back_query"]),
                "aggs": {"t": {"terms": {"field": field, "size": len(chunk), "include": chunk},
                               "aggs": m_aggs}}}
        r = ctx.search(body, f"calculating each {singular(plan['entity'])}'s works")
        return r["aggregations"]["t"]["buckets"]

    def total():
        body = {"size": 0, "track_total_hits": True, "query": plan["works_query"],
                "aggs": m_aggs}
        return ctx.search(body, f"calculating all their works together")

    tasks = [("p", c) for c in chunks] + [("t", None)]
    results = _pmap(lambda t: part(t[1]) if t[0] == "p" else total(), tasks)
    total_res = results[-1]
    seen = {}
    for buckets in results[:-1]:
        for b in buckets:
            seen[b["key"]] = b
    rows = []
    for k in keys:
        b = seen.get(k)
        count = b["doc_count"] if b else 0
        row = {"key": k, "key_display_name": None, "count": count}
        for m in measures:
            if m.measure != "count":
                row[m.key] = A._measure_value(m, b or {}, count, None)
        rows.append(row)
    sort = None
    if oqo.sort_by:
        s0 = oqo.sort_by[0]
        sort = (s0.column_id, s0.direction or "desc")
    if sort and sort[0] != "count":
        rows = A._sort_rows(rows, sort)
    else:
        desc = not sort or sort[1] == "desc"
        rows.sort(key=lambda r: ((-r["count"] if desc else r["count"]), str(r["key"])))
    per_page = oqo.per_page or A.DEFAULT_PER_PAGE
    page = oqo.page or 1
    start = (page - 1) * per_page
    page_rows = rows[start:start + per_page]
    _name(page_rows, ctx)
    total_count = total_res["hits"]["total"]["value"]
    total_row = {"key": "all", "key_display_name": f"all their works", "count": total_count}
    for m in measures:
        if m.measure != "count":
            total_row[m.key] = A._measure_value(m, total_res.get("aggregations", {}),
                                                total_count, None)
    meta = _meta(oqo, ctx, count=total_count, groups=len(rows))
    meta.update(page=page, per_page=per_page, more_groups=start + per_page < len(rows),
                measures=[A._measure_meta(m, "works") for m in measures])
    return {"meta": meta, "summary": {"all": total_row}, "group_by": page_rows, "results": []}


def _name(rows: List[dict], ctx: Ctx):
    """Display names for the returned rows only."""
    keys = [r["key"] for r in rows if isinstance(r["key"], str)]
    names = {}
    if keys and all(k.startswith(A.ID_PREFIX) for k in keys):
        try:
            names = A._id_names(keys, ctx.connection) or {}
        except Exception:
            names = {}
    for r in rows:
        r["key_display_name"] = names.get(r["key"]) or str(r["key"])


def _meta(oqo: OQO, ctx: Ctx, count: int, groups: Optional[int]) -> dict:
    return {"count": count, "groups_count": groups, "page": None, "per_page": None,
            "more_groups": False, "next_cursor": None, "measures": [],
            "es_calls": ctx.deadline.calls, "elapsed_ms": ctx.deadline.elapsed_ms(),
            "steps": ctx.deadline.log, "cost": walk_price(oqo, ctx.deadline.calls)}


def check(oqo: OQO, connection) -> dict:
    """The free `/query` check for walks and sets: limits with their fixes, the time
    estimate against the budget, the price. One cheap count per walk or set (how
    many things or works it would list); never the walk itself."""
    ctx = Ctx(connection, A.Deadline())
    limits: List[dict] = []
    est, calls, note = EST_OVERHEAD_S, 1, None

    def add_set(inner: OQO, column: str):
        nonlocal est, calls, note
        try:
            if column == "cited_by":
                n = count_distinct(ctx, _works_query(inner, ctx), "referenced_works",
                                   "counting the set's references")
            elif result_entity(inner) == "works" and not inner.walks:
                n = ctx.search({"size": 0, "track_total_hits": True,
                                "query": _works_query(inner, ctx)},
                               "counting the set")["hits"]["total"]["value"]
            elif inner.walks and inner.walks[-1].to is None:
                link = inner.walks[-1].column_id
                n = count_distinct(ctx, _works_query(inner, ctx), ctx.raw_field(link),
                                   "counting the set")
            else:
                note = "the size of a set that walks out and back is known only when it runs"
                return
        except A.AnalyticsError as e:
            limits.append(e.to_dict())
            return
        calls += 2 + math.ceil(n / 10_000) + 1     # year split, pages, no-year, count
        est += n / EST_IDS_PER_S + n / EST_FILTER_IDS_PER_S
        if n > MAX_SET_IDS:
            limits.append(_too_big("uses a set of {n} ids", n, MAX_SET_IDS,
                                   "Narrow the query in parentheses (a shorter year range, a "
                                   "smaller institution or topic), or save the set as a "
                                   "collection.").to_dict())

    def visit(node):
        if isinstance(node, BranchFilter):
            for f in node.filters:
                visit(f)
        elif isinstance(node, LeafFilter) and isinstance(node.value, OQO):
            add_set(node.value, node.column_id)
        elif isinstance(node, LeafFilter) and node.column_id in RELATION_COLUMNS:
            nonlocal est, calls
            calls += 1                     # one group-by lists the co-authors
            est += A.EST_COAUTHOR_S
    for f in oqo.filter_rows:
        visit(f)
    for w in oqo.walks:
        if w.where is not None:
            visit(w.where)
    out = next((w for w in oqo.walks if w.to is None), None)
    back = next((w for w in oqo.walks if w.to is not None), None)
    if out is not None and (back is not None or oqo.calculate or out.where is not None):
        entity = entity_for_link(out.column_id)
        try:
            n = count_distinct(ctx, _works_query(replace(oqo, filter_rows=[
                f for f in oqo.filter_rows if not has_query_value(f)]), ctx),
                ctx.raw_field(out.column_id), f"counting the {plural(entity)}")
        except A.AnalyticsError as e:
            limits.append(e.to_dict())
            n = 0
        if back is None and not out.where and oqo.calculate:
            # a distinct count: exact listing while it fits, else one approximate call
            if n <= EXACT_COUNT_MAX:
                est += n / 200_000
                calls += math.ceil(n * 1.15 / LIST_PART)
        else:
            est += n / EST_THINGS_PER_S
            size = max(1_000, min(PART_THINGS, math.ceil(max(n, 1) / INFLIGHT)))
            calls += (math.ceil(n * 1.15 / LIST_PART) + math.ceil(n / size) + 1
                      + (math.ceil(n / 10_000) if out.where is not None else 0))
    estimate = {"seconds": round(est, 1), "es_calls": calls,
                "budget_seconds": A.TIME_BUDGET_S, "within_budget": est <= A.TIME_BUDGET_S}
    if est > A.TIME_BUDGET_S and not any(x["error"] == "query_too_slow" for x in limits):
        limits.append({"error": "query_too_slow",
                       "message": (f"This query is estimated at {est:,.0f} seconds; queries "
                                   f"get about {int(A.TIME_BUDGET_S)}."),
                       "fix": ("Narrow the starting works (a shorter year range, a smaller "
                               "institution or topic), or filter the things you walk to "
                               "(get each author of those works where ...).")})
    if limits:
        estimate["within_budget"] = False
    out_d = {"valid": not limits, "limits": limits, "estimate": estimate,
             "cost": walk_price(oqo, calls)}
    if note:
        out_d["note"] = note
    return out_d


def walk_price(oqo: OQO, calls: Optional[int] = None) -> dict:
    """Credits from the plan: the starting set as Rung 1 prices it, plus one credit
    for each further call the walk or set makes (a list of 168,000 authors and their
    works is about 15 calls)."""
    from dataclasses import replace as _r
    base = A.price(_r(oqo, walks=[], each=False,
                      filter_rows=[f for f in oqo.filter_rows if not has_query_value(f)]))
    steps = list(base["steps"])
    extra = max(0, (calls or 0) - 1) if calls is not None else 2
    if extra:
        steps.append({"what": f"walks and sets: {extra} more call{'s' if extra > 1 else ''}",
                      "credits": extra * A.LOOKUP_CREDITS})
    credits = sum(s["credits"] for s in steps)
    return {"credits": credits, "usd": round(credits * A.CREDIT_USD, 6), "steps": steps}
