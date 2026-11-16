"""/links (oxjob #1490): work-to-work links. A link joins two works and has a relationship from /relationships:
`citation`, or one of the part-of kinds a work's parent_works carries (volume, component, data-series, part).

Links are read from the works index at request time, so every request names a work:

    /links?filter=from:W1          the work's links out: its parent works, then the works it cites (reference order)
    /links?filter=to:W2            the works that link to it, newest first
    /links?filter=from:W1,to:W2    the links between the two
    relationship:citation          (any of the three) keeps one kind; values join with |

Every work counts, whatever the works default view leaves out: a link is a fact about two works, and part-of links
mostly lead to pieces (figures, chapters) that the default view hides.
"""
import time

from elasticsearch_dsl import Q, Search
from flask import Blueprint, jsonify, request

from combined_config import all_entities_config
from core.cursor import decode_cursor, encode_cursor
from core.exceptions import APIPaginationError, APIQueryParamsError
from core.merged_ids import merged_winner, note_resolved, resolved_in_request
from core.paginate import Paginate
from core.utils import normalize_openalex_id, set_number_param
from settings import WORKS_INDEX

blueprint = Blueprint("links", __name__)

URL = "https://openalex.org/"
CITATION = "citation"
RELATIONSHIPS = [v["id"].split("/")[-1] for v in all_entities_config["relationships"]["values"]]
PART_OF = [r for r in RELATIONSHIPS if r != CITATION]
FILTER_KEYS = ("from", "to", "relationship")
UNSUPPORTED_PARAMS = ("group_by", "group-by", "sort", "search", "select", "sample")
EXAMPLES = (
    "Name a work: /links?filter=from:W2741809807 lists the works it is part of and the works it cites; "
    "/links?filter=to:W2741809807 lists the works that cite it or are part of it. "
    f"Add relationship:citation (or {', '.join(PART_OF)}) to keep one kind."
)


def parse_filter(filter_string):
    """{"from": W, "to": W, "relationship": [...]} from a filter string; a 400 for anything else."""
    named = {}
    for clause in filter(None, (c.strip() for c in (filter_string or "").split(","))):
        key, sep, value = clause.partition(":")
        key = key.strip().lower()
        if not sep or key not in FILTER_KEYS:
            raise APIQueryParamsError(f"/links filters are from, to and relationship, not '{clause}'. {EXAMPLES}")
        if key in named:
            raise APIQueryParamsError(f"{key} is given twice. {EXAMPLES}")
        named[key] = value.strip()
    if not named.get("from") and not named.get("to"):
        raise APIQueryParamsError(EXAMPLES)
    parsed = {key: work_id(named[key], key) for key in ("from", "to") if named.get(key)}
    parsed["relationship"] = relationships(named.get("relationship"))
    return parsed


def work_id(value, key):
    short = normalize_openalex_id(value)
    if not short or not short.startswith("W") or "|" in value or value.startswith("!"):
        raise APIQueryParamsError(f"{key} takes one work id, such as W2741809807, not '{value}'. {EXAMPLES}")
    return short


def relationships(value):
    """The relationships asked for, in vocabulary order; all of them when none is named."""
    if not value:
        return list(RELATIONSHIPS)
    asked = {v.strip().rstrip("/").split("/")[-1].lower() for v in value.split("|")}
    unknown = sorted(asked - set(RELATIONSHIPS))
    if unknown or value.startswith("!"):
        raise APIQueryParamsError(
            f"relationship takes {', '.join(RELATIONSHIPS)} (join several with |), not '{value}'.")
    return [r for r in RELATIONSHIPS if r in asked]


def resolve(short):
    """The surviving work for a merged-away id, noted for meta.merged_ids; the id itself otherwise."""
    winner = merged_winner(short)
    if winner:
        note_resolved({short: winner})
    return winner or short


def outgoing_links(doc, kinds):
    """(to_id, to_display_name, relationship) for every link out of a works doc: parents first, then references."""
    links = [(p.get("id"), p.get("display_name"), p.get("relationship"))
             for p in doc.get("parent_works") or [] if p.get("relationship") in kinds]
    if CITATION in kinds:
        links += [(w, None, CITATION) for w in doc.get("referenced_works") or []]
    return links


def incoming_query(targets, kinds):
    """Works that link to any of `targets` (full ids) by one of `kinds`. The citation clause is named, so each hit
    says whether it cites; its part-of links are read from its parent_works."""
    clauses = []
    if CITATION in kinds:
        clauses.append(Q("terms", referenced_works=targets, _name=CITATION))
    parts = [k for k in kinds if k != CITATION]
    if parts:
        part_of = Q("terms", **{"parent_works.id": targets})
        if parts != PART_OF:
            part_of &= Q("terms", **{"parent_works.relationship": parts})
        clauses.append(part_of)
    return Q("bool", should=clauses, minimum_should_match=1)


def incoming_links(source, matched_queries, targets, kinds):
    """The relationships by which one linking work (a hit's source) links to `targets`: parents first, as out."""
    rels = [p.get("relationship") for p in source.get("parent_works") or []
            if p.get("id") in targets and p.get("relationship") in kinds]
    if CITATION in (matched_queries or []):
        rels.append(CITATION)
    return rels


def work_ref(work_id, display_name):
    return {"id": work_id, "display_name": display_name}


def link(from_ref, to_ref, relationship):
    return {"from": from_ref, "to": to_ref, "relationship": relationship}


def display_names(ids):
    """{full id: display_name} for the works among `ids` that exist."""
    ids = [i for i in dict.fromkeys(ids) if i]
    if not ids:
        return {}
    s = Search(index=WORKS_INDEX).query(Q("ids", values=ids)).source(["id", "display_name"]).extra(size=len(ids))
    return {h.id: h.display_name for h in s.execute().hits}


def get_work(full_id, fields):
    s = Search(index=WORKS_INDEX).query(Q("ids", values=[full_id])).source(fields).extra(size=1)
    hits = s.execute().hits
    return hits[0].to_dict() if hits else None


def paging():
    page = set_number_param(request, "page", 1)
    per_page = set_number_param(request, "per-page", 25)
    cursor = request.args.get("cursor")
    paginate = Paginate(None, page, per_page)
    paginate.validate_page()
    paginate.validate_per_page()
    if cursor:
        if page != 1:
            raise APIPaginationError("Cannot use page parameter with cursor.")
    else:
        paginate.validate_result_size()
    return page, per_page, cursor


def offset_from_cursor(cursor):
    if cursor == "*":
        return 0
    values = decode_cursor(cursor)
    if len(values) != 1 or not isinstance(values[0], int) or values[0] < 0:
        raise APIPaginationError("Invalid cursor value")
    return values[0]


def links_from(parsed, page, per_page, cursor):
    """Links out of one work, optionally only those to a second work: a slice of its stored lists."""
    from_id = URL + resolve(parsed["from"])
    doc = get_work(from_id, ["id", "display_name", "parent_works", "referenced_works"])
    links = outgoing_links(doc, parsed["relationship"]) if doc else []
    if "to" in parsed:
        to_short = parsed["to"]
        targets = {URL + to_short, URL + resolve(to_short)}
        links = [lk for lk in links if lk[0] in targets]
    start = offset_from_cursor(cursor) if cursor else (page - 1) * per_page
    shown = links[start:start + per_page]
    names = display_names([lk[0] for lk in shown if lk[1] is None])
    from_ref = work_ref(doc["id"], doc.get("display_name")) if doc else None
    results = [link(from_ref, work_ref(to, name if name is not None else names.get(to)), rel)
               for to, name, rel in shown]
    next_cursor = encode_cursor([start + per_page]) if cursor and start + per_page < len(links) else None
    return len(links), results, next_cursor


def links_to(parsed, page, per_page, cursor):
    """Links into one work: a works search, newest linking work first."""
    asked = parsed["to"]
    to_short = resolve(asked)
    to_id = URL + to_short
    targets = list(dict.fromkeys([URL + asked, to_id]))
    kinds = parsed["relationship"]
    s = (Search(index=WORKS_INDEX)
         .query(incoming_query(targets, kinds))
         .source(["id", "display_name", "parent_works"])
         .sort({"publication_date": {"order": "desc", "missing": "_last"}}, {"id": {"order": "desc"}})
         .extra(track_total_hits=True))
    if cursor:
        if cursor != "*":
            s = s.extra(search_after=decode_cursor(cursor))
        s = s.extra(size=per_page + 1)  # one past the page: is there a next one?
    else:
        s = s[(page - 1) * per_page:page * per_page]
    response = s.execute()
    hits = list(response.hits)
    more = cursor and len(hits) > per_page
    hits = hits[:per_page]
    to_ref = work_ref(to_id, display_names([to_id]).get(to_id))
    results = [link(work_ref(h.id, h.to_dict().get("display_name")), to_ref, rel)
               for h in hits
               for rel in incoming_links(h.to_dict(), getattr(h.meta, "matched_queries", None), targets, kinds)]
    next_cursor = encode_cursor(list(hits[-1].meta.sort)) if more else None
    return response.hits.total.value, results, next_cursor


@blueprint.route("/links")
def links():
    started = time.time()
    for param in UNSUPPORTED_PARAMS:
        if request.args.get(param) is not None:
            raise APIQueryParamsError(f"/links does not take {param}. {EXAMPLES}")
    parsed = parse_filter(request.args.get("filter"))
    page, per_page, cursor = paging()
    if "from" in parsed:
        count, results, next_cursor = links_from(parsed, page, per_page, cursor)
    else:
        count, results, next_cursor = links_to(parsed, page, per_page, cursor)
    meta = {
        "count": count,
        "db_response_time_ms": int((time.time() - started) * 1000),
        "page": None if cursor else page,
        "per_page": per_page,
        "next_cursor": next_cursor,
    }
    merged = resolved_in_request()
    if merged:
        meta["merged_ids"] = merged
    return jsonify({"meta": meta, "results": results})
