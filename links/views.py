"""/links (oxjob #1490): work-to-work links. A link is three ids: `origin` (the work that holds the link: the citing
paper, the chapter), `target` (the work it points to) and `relationship` (a /relationships id). Field names: Jason,
17 Nov; three ids with no display names: Casey + Jason, 17 Nov.

Links are read from the `links` index: one doc per link, built nightly from openalex.works.work_links by walden's
Work Links job (20 Nov 2026). Every request names a work:

    /links?filter=origin:W1            the work's links out
    /links?filter=target:W2            the works that link to it
    /links?filter=origin:W1,target:W2  the links between the two
    relationship:citation              (any of the three) keeps one kind; values join with |

Order: part-of links first (a work's parents, or its figures and chapters), then the rest, each by the other work's id.
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
from settings import LINKS_INDEX

blueprint = Blueprint("links", __name__)

URL = "https://openalex.org/"
RELATIONSHIPS = [v["id"].split("/")[-1] for v in all_entities_config["relationships"]["values"]]
PART_OF = ["volume", "component", "data-series", "part"]  # listed first (Casey, 17 Nov)
FILTER_KEYS = ("origin", "target", "relationship")
UNSUPPORTED_PARAMS = ("group_by", "group-by", "sort", "search", "select", "sample")
EXAMPLES = (
    "Name a work: /links?filter=origin:W2741809807 lists the works it is part of and the works it cites; "
    "/links?filter=target:W2741809807 lists the works that cite it or are part of it. "
    f"Add relationship:citation (or {', '.join(PART_OF)}) to keep one kind."
)


def parse_filter(filter_string):
    """{"origin": W, "target": W, "relationship": [...]} from a filter string; a 400 for anything else."""
    named = {}
    for clause in filter(None, (c.strip() for c in (filter_string or "").split(","))):
        key, sep, value = clause.partition(":")
        key = key.strip().lower()
        if not sep or key not in FILTER_KEYS:
            raise APIQueryParamsError(f"/links filters are origin, target and relationship, not '{clause}'. {EXAMPLES}")
        if key in named:
            raise APIQueryParamsError(f"{key} is given twice. {EXAMPLES}")
        named[key] = value.strip()
    if not named.get("origin") and not named.get("target"):
        raise APIQueryParamsError(EXAMPLES)
    parsed = {key: work_id(named[key], key) for key in ("origin", "target") if named.get(key)}
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


def links_query(parsed):
    """The links of the named work(s) by the asked relationships. Part-of links score higher, so they come first."""
    rel_ids = [URL + "relationships/" + r for r in parsed["relationship"]]
    must = [Q("terms", relationship=rel_ids)]
    for key in ("origin", "target"):
        if key in parsed:
            asked = parsed[key]
            must.append(Q("terms", **{key: list(dict.fromkeys([URL + asked, URL + resolve(asked)]))}))
    parts = [URL + "relationships/" + r for r in PART_OF]
    return Q("bool", filter=must, should=[Q("constant_score", filter=Q("terms", relationship=parts), boost=1)])


def sort_for(parsed):
    other = "target" if "origin" in parsed else "origin"
    return ({"_score": {"order": "desc"}}, {other: {"order": "asc"}}, {"relationship": {"order": "asc"}})


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


def find_links(parsed, page, per_page, cursor):
    s = (Search(index=LINKS_INDEX)
         .query(links_query(parsed))
         .sort(*sort_for(parsed))
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
    results = [{"origin": h.origin, "target": h.target, "relationship": h.relationship} for h in hits]
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
    count, results, next_cursor = find_links(parsed, page, per_page, cursor)
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
