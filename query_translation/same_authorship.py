"""Facts about one authorship: one person's place on one work (oxjob #2537).

An authorship carries its own facts: the person, the institutions they listed on
that work, their contributor roles (CRediT's 14, editor, translator). The works index
holds authorships as flat arrays (`authorships_full.*`, no nested fields), so a works
filter on two of them pairs nothing: `author is A1` and `role is software` match a
work where A1 is on it and *someone* did the software. Two kinds of question need the
pairing:

* a works list, `get works with [Jane Smith](A1) in the role [Software](software)`:
  an `AuthorshipFilter` in the filter rows, kept only where ONE authorship meets every
  condition (`resolve_rows`);
* a people table, `get the count of works about kelp by author listing [UBC](I1) on the
  work`: a split by author whose `GroupBy.same_authorship` conditions pick, on each
  work, the authorships that count (`split_by_authorship`).

Both read the works that could match (the query's other conditions plus the flat
superset of these: every condition met by some authorship) and check each one's
authorships in `_source.authorships_full` (never `authorships`, which stops at 100).
The superset is never the answer. Capped like #1555's record check: up to
CANDIDATE_LIMIT works and SEAT_LIMIT authorships read, loud past either. The validator
admits only plain leaves on SAME_AUTHORSHIP_FACTS here, one split, the count.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import replace
from typing import Callable, List, Optional, Tuple

from query_translation import analytics as A
from query_translation.oqo import (OQO, PERSON_COLUMN, SAME_AUTHORSHIP_FACTS, AuthorshipFilter, LeafFilter,
                                   Measure, authorship_full_value, authorship_nodes, has_query_value,
                                   has_relation_leaf)

# Works checked a query, and authorships read: 5,000 works is #1555's record-check cap;
# the authorships one keeps a few hyperauthored papers (up to ~5,000 authorships each)
# from making the read slow. A page holds about PAGE_SEATS authorships (at most
# PAGE_WORKS works) and is reduced as it arrives: what a worker holds at once.
CANDIDATE_LIMIT = 5_000
SEAT_LIMIT = 250_000
PAGE_SEATS = 20_000
PAGE_WORKS = 1_000
# Measured in-process from desk against production (22 Nov 2026), reading page by page:
# 3,642 CERN works (under 1,000 authors each) in 2.3 s; 1,588 Harvard ones in 1.7 s.
EST_WORKS_PER_S = 2_000

NARROW = ("Narrow the works (a shorter year range, a topic, a journal, a smaller institution), so "
          "fewer than {limit:,} could match.").format(limit=CANDIDATE_LIMIT)


def needs_check(tree) -> bool:
    """A filter tree holding conditions that pair facts on one authorship."""
    return any(n.pairs for n in authorship_nodes(tree))


# ---------------------------------------------------------------------------
# One authorship
# ---------------------------------------------------------------------------
def _holds(x, path: Tuple[str, ...], want: str) -> bool:
    """Does `x` (an authorship, or part of one) hold `want` at `path`, through lists?"""
    if isinstance(x, list):
        return any(_holds(y, path, want) for y in x)
    if not path:
        return x == want
    return isinstance(x, dict) and _holds(x.get(path[0]), path[1:], want)


def matcher(node: AuthorshipFilter) -> Callable[[dict], bool]:
    """A test of one authorship against every fact of `node`, prepared once."""
    facts = [(SAME_AUTHORSHIP_FACTS[f.column_id][2], authorship_full_value(f.column_id, f.value))
             for f in node.filters]
    return lambda seat: all(_holds(seat, path, want) for path, want in facts)


def superset_query(node: AuthorshipFilter) -> dict:
    """The works where some authorship meets each fact (not necessarily the same one):
    a superset of the answer, never the answer; for a single fact, the answer."""
    return {"bool": {"filter": [
        {"term": {SAME_AUTHORSHIP_FACTS[f.column_id][1]: authorship_full_value(f.column_id, f.value)}}
        for f in node.filters]}}


# ---------------------------------------------------------------------------
# The works that could match: counted (with the caps), then read
# ---------------------------------------------------------------------------
def _limit_errors(n: int, seats: int, what: str) -> List[A.AnalyticsError]:
    if n > CANDIDATE_LIMIT:
        return [A.AnalyticsError(
            "too_many_works_to_check",
            f"About {n:,} works could match {what}; a condition on one person's place on a work "
            f"checks each work's authors, up to {CANDIDATE_LIMIT:,} works a query.", NARROW)]
    if seats > SEAT_LIMIT:
        return [A.AnalyticsError(
            "too_many_authors_to_check",
            f"The {n:,} works that could match {what} list {seats:,} authors between them; a "
            f"condition on one person's place on a work reads up to {SEAT_LIMIT:,} a query.",
            NARROW + " Papers with thousands of authors fill it fastest: `where authors count is "
            "below 1000` leaves them out.")]
    return []


def _count(ctx, query: dict, what: str) -> Tuple[int, int]:
    """(the works `query` matches, the authors they list between them): one call."""
    r = ctx.search({"size": 0, "track_total_hits": True, "query": query,
                    "aggs": {"seats": {"sum": {"field": "authors_count"}}}}, f"counting the works {what}")
    return r["hits"]["total"]["value"], int(r["aggregations"]["seats"]["value"] or 0)


def scan(ctx, base: Optional[dict], node: AuthorshipFilter, what: str,
         keep: Callable[[str, List[dict]], Optional[object]]) -> List:
    """`keep(work id, its authorships)` for every work that could match `node` within
    `base`, the non-None results in a list. Every such condition in one query draws on
    one budget of CANDIDATE_LIMIT works and SEAT_LIMIT authorships, loud past either.
    One pass over the candidates sorted by id (search_after reads every one, whatever was
    indexed since the count), each page sized to hold about PAGE_SEATS authorships and
    reduced as it arrives, so a worker holds one page of authorships at a time."""
    query = A._and(base, superset_query(node))
    n, seats = _count(ctx, query, what)
    used_n, used_seats = getattr(ctx, "same_authorship_read", (0, 0))
    for e in _limit_errors(used_n + n, used_seats + seats, what):
        raise e
    ctx.same_authorship_read = (used_n + n, used_seats + seats)
    size = max(1, min(PAGE_WORKS, PAGE_SEATS * max(n, 1) // max(seats, 1)))
    fields = ["id"] + sorted({SAME_AUTHORSHIP_FACTS[c][1] for c in
                              {f.column_id for f in node.filters} | {PERSON_COLUMN}})
    out, after = [], None
    while True:
        body = {"size": size, "query": query, "_source": fields, "sort": [{"id": "asc"}],
                "track_total_hits": False}
        if after is not None:
            body["search_after"] = after
        hits = ctx.search(body, f"reading the authors of the works {what}")["hits"]["hits"]
        for h in hits:
            v = keep(h["_source"]["id"], h["_source"].get("authorships_full") or [])
            if v is not None:
                out.append(v)
        if len(hits) < size:
            return out
        after = hits[-1]["sort"]


def _top_supersets(rows: List) -> List[dict]:
    """The supersets of the query's top-level pairing conditions: the answer is inside
    each, so every condition's candidates can be narrowed by all of them."""
    return [superset_query(r) for r in rows if isinstance(r, AuthorshipFilter) and r.pairs and not r.is_negated]


# ---------------------------------------------------------------------------
# A works list: `get works with [Jane Smith](A1) in the role [Software](software)`
# ---------------------------------------------------------------------------
def matching_works(ctx, node: AuthorshipFilter, base: Optional[dict]) -> List[str]:
    """The works (within `base`, the query's other conditions) where one authorship
    meets every fact of `node`."""
    match = matcher(node)
    return scan(ctx, base, node, "these conditions on one author",
                lambda w, seats: w if any(match(s) for s in seats) else None)


def _label(node: AuthorshipFilter) -> str:
    """What the resolved set echoes as (IdSet.label); a label never fails the query."""
    from query_translation.oql_core import NotCore, authorship_phrase
    try:
        return authorship_phrase(replace(node, is_negated=False))
    except NotCore:
        return "works where one author meets every condition"


def resolve_rows(oqo: OQO, rows: List, ctx) -> List:
    """Each pairing AuthorshipFilter in a works query's filter rows becomes the ids of the
    works it keeps. The candidates are narrowed by the query's other top-level conditions:
    whatever the tree, the answer is inside them, so the ids decide only there."""
    if not any(needs_check(r) for r in rows):
        return rows
    from query_translation.walk_exec import IdSet, _works_query
    base = A._and(_works_query(replace(oqo, filter_rows=[r for r in rows if not needs_check(r)]), ctx),
                  *_top_supersets(rows))

    def walk(node):
        if isinstance(node, AuthorshipFilter) and node.pairs:
            return LeafFilter("ids.openalex", IdSet(matching_works(ctx, node, base), _label(node)),
                              "in", node.is_negated)
        if needs_check(node):
            return replace(node, filters=[walk(f) for f in node.filters])
        return node
    return [walk(r) for r in rows]


# ---------------------------------------------------------------------------
# A people table: `get the count of works about kelp by author listing [UBC](I1) on the work`
# ---------------------------------------------------------------------------
def split_by_authorship(oqo: OQO, ctx) -> dict:
    """One row per person, counting the works where that person's own authorship meets
    the split's conditions (the validator admits one such split and the count only)."""
    from query_translation import walk_exec as WX
    node = AuthorshipFilter(filters=list(oqo.group_by[0].same_authorship))
    base = WX._works_query(replace(oqo, group_by=[], calculate=[], sort_by=[]), ctx)
    match = matcher(node)
    counts: Counter = Counter()

    def keep(_work, seats):
        counts.update({(s.get("author") or {}).get("id") for s in seats if match(s)} - {None})
    scan(ctx, base, node, "the split's conditions on one author", keep)
    total = WX._count(ctx, base or {"match_all": {}}, "counting the works")
    rows = [{"key": k, "key_display_name": None, "count": c} for k, c in counts.items()]
    body = WX.table_body(oqo, ctx, rows, {"key": "all", "key_display_name": "all works", "count": total},
                         [Measure("count")])
    body["meta"]["rows_count"] = len(rows)
    return body


# ---------------------------------------------------------------------------
# The free check (`/query` check, walk_exec.check): one count, never the reading
# ---------------------------------------------------------------------------
def check(oqo: OQO, ctx) -> Tuple[List[dict], float, int]:
    """(limits, seconds, ES calls) for the query's conditions on one authorship. A query
    whose other conditions hold sets or relations is counted without them (they resolve
    only when it runs): its count is a ceiling, so it estimates but never refuses."""
    from query_translation.walk_exec import _works_query
    nodes = [n for f in oqo.filter_rows for n in authorship_nodes(f) if n.pairs]
    nodes += [AuthorshipFilter(filters=list(g.same_authorship)) for g in oqo.group_by if g.same_authorship]
    if not nodes:
        return [], 0.0, 0
    wider = any(has_query_value(f) or has_relation_leaf(f) for f in oqo.filter_rows)
    plain = [f for f in oqo.filter_rows
             if not needs_check(f) and not has_query_value(f) and not has_relation_leaf(f)]
    base = A._and(_works_query(replace(oqo, filter_rows=plain, group_by=[], calculate=[], sort_by=[]), ctx),
                  *_top_supersets(oqo.filter_rows))
    what = "the conditions on one author"
    used_n = used_seats = calls = 0
    for node in nodes:
        try:
            n, seats = _count(ctx, A._and(base, superset_query(node)), what)
        except A.AnalyticsError as e:
            return [e.to_dict()], 0.0, calls
        used_n, used_seats = used_n + n, used_seats + seats
        read = min(n, CANDIDATE_LIMIT)
        calls += 1 + max(1, -(-read * max(seats, 1) // max(n, 1) // PAGE_SEATS))
    limits = [] if wider else [e.to_dict() for e in _limit_errors(used_n, used_seats, what)]
    return limits, min(used_n, CANDIDATE_LIMIT) / EST_WORKS_PER_S, calls
