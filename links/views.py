"""/links (oxjob #1490): work-to-work links. A link is three ids: `origin` (the work that holds the link: the citing
paper, the chapter, the review, the retraction notice), `target` (the work it points to) and `relationship` (a
/relationships id). Field names: Jason, 17 Nov; three ids with no display names: Casey + Jason, 17 Nov. `link_type`
(oxjob #2481) is the new name of `relationship`: the same kind as a /link-types id; both are served, and filter on
either, until the cutover.

Links are read from the `links` index: one doc per link, built nightly from openalex.works.work_links by walden's
Work Links job (20 Nov 2026). Every request names a work:

    /links?filter=origin:W1            the work's links out
    /links?filter=target:W2            the works that link to it
    /links?filter=origin:W1,target:W2  the links between the two
    link_type:citation                 (any of the three) keeps one kind; values join with |
                                       (relationship:citation, its old name, still works)

No order is promised yet (Casey, 21 Nov: "leave it unsorted"): results come in the index's own order, which is the cheap
way to page (a sort on the ids took 5-7 s for a work with 334K links). Cursor walks use a point-in-time view.
"""
import time

from elasticsearch import NotFoundError
from elasticsearch_dsl import Q, Search
from elasticsearch_dsl.connections import get_connection
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
PART_OF = ["volume", "component", "data-series", "part"]
# oxjob #2264: pull notices. The notice is the origin, the work it pulled the target.
PULL_NOTICES = ["retraction", "withdrawal", "removal"]
# The kind of link: `link_type` (oxjob #2481) or its old name `relationship`, never both.
KIND_KEYS = ("link_type", "relationship")
FILTER_KEYS = ("origin", "target") + KIND_KEYS
UNSUPPORTED_PARAMS = ("group_by", "group-by", "sort", "search", "select", "sample")
EXAMPLES = (
    "Name a work: /links?filter=origin:W2741809807 lists the works it is part of, cites, reviews or pulls (as a "
    "retraction, withdrawal or removal notice); /links?filter=target:W2741809807 lists the works that cite it, "
    "review it, pull it or are part of it. "
    f"Add link_type:citation (or review, {', '.join(PULL_NOTICES + PART_OF)}) to keep one kind."
)


def parse_filter(filter_string):
    """{"origin": W, "target": W, "relationship": [...]} from a filter string; a 400 for anything else."""
    named = {}
    for clause in filter(None, (c.strip() for c in (filter_string or "").split(","))):
        key, sep, value = clause.partition(":")
        key = key.strip().lower()
        if not sep or key not in FILTER_KEYS:
            raise APIQueryParamsError(
                f"/links filters are origin, target and link_type (relationship is its old name), not '{clause}'. "
                f"{EXAMPLES}")
        if key in named:
            raise APIQueryParamsError(f"{key} is given twice. {EXAMPLES}")
        named[key] = value.strip()
    if all(key in named for key in KIND_KEYS):
        raise APIQueryParamsError(
            "Give link_type or relationship, not both: relationship is the old name of link_type. Use link_type.")
    if not named.get("origin") and not named.get("target"):
        raise APIQueryParamsError(EXAMPLES)
    parsed = {key: work_id(named[key], key) for key in ("origin", "target") if named.get(key)}
    kind_key = "relationship" if "relationship" in named else "link_type"
    parsed["relationship"] = relationships(named.get(kind_key), kind_key)
    return parsed


def work_id(value, key):
    short = normalize_openalex_id(value)
    if not short or not short.startswith("W") or "|" in value or value.startswith("!"):
        raise APIQueryParamsError(f"{key} takes one work id, such as W2741809807, not '{value}'. {EXAMPLES}")
    return short


def relationships(value, key="relationship"):
    """The kinds of link asked for, in vocabulary order; all of them when none is named. A value is the key
    (`citation`) or either id: https://openalex.org/link-types/citation or its old form .../relationships/citation."""
    if not value:
        return list(RELATIONSHIPS)
    asked = {v.strip().rstrip("/").split("/")[-1].lower() for v in value.split("|")}
    unknown = sorted(asked - set(RELATIONSHIPS))
    if unknown or value.startswith("!"):
        raise APIQueryParamsError(
            f"{key} takes {', '.join(RELATIONSHIPS)} (join several with |), not '{value}'.")
    return [r for r in RELATIONSHIPS if r in asked]


def resolve(short):
    """The surviving work for a merged-away id, noted for meta.merged_ids; the id itself otherwise."""
    winner = merged_winner(short)
    if winner:
        note_resolved({short: winner})
    return winner or short


def links_query(parsed):
    """The links of the named work(s), by the asked relationships. The work ids filter; a relationship asked for is a
    `must`, never a filter: a relationship matches most of the index, and the filter cache would build a bitset over
    billions of links for it (5 s cold, 21 Nov 2026). Asking for every relationship adds no clause."""
    filters = []
    for key in ("origin", "target"):
        if key in parsed:
            asked = parsed[key]
            filters.append(Q("terms", **{key: list(dict.fromkeys([URL + asked, URL + resolve(asked)]))}))
    must = []
    if parsed["relationship"] != RELATIONSHIPS:
        must.append(Q("terms", relationship=[URL + "relationships/" + r for r in parsed["relationship"]]))
    return Q("bool", filter=filters, must=must)


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


PIT_KEEP_ALIVE = "5m"


def open_pit():
    return get_connection().open_point_in_time(index=LINKS_INDEX, keep_alive=PIT_KEEP_ALIVE)["id"]


def close_pit(pit_id):
    try:
        get_connection().close_point_in_time(id=pit_id)
    except Exception:
        pass  # it expires on its own


def find_links(parsed, page, per_page, cursor):
    """No order is promised. Pages read the index in its stored order. A cursor walk reads a point-in-time view of the
    index in shard order, so the nightly writes and the merges after them can't shift it."""
    query = links_query(parsed)
    if not cursor:
        s = Search(index=LINKS_INDEX).query(query).sort("_doc").extra(track_total_hits=True)
        response = s[(page - 1) * per_page:page * per_page].execute()
        return response.hits.total.value, [as_link(h) for h in response.hits], None
    if cursor == "*":
        pit_id, after = open_pit(), None
    else:
        values = decode_cursor(cursor)
        if len(values) != 2 or not isinstance(values[0], str):
            raise APIPaginationError("Invalid cursor value")
        pit_id, after = values
    s = (Search().query(query).sort("_shard_doc")
         .extra(pit={"id": pit_id, "keep_alive": PIT_KEEP_ALIVE}, size=per_page + 1, track_total_hits=True))
    if after is not None:
        s = s.extra(search_after=after)
    try:
        response = s.execute()
    except NotFoundError:
        raise APIPaginationError("This cursor has expired (a walk must ask for its next page within 5 minutes). "
                                 "Start again with cursor=*.")
    pit_id = response._d_.get("pit_id", pit_id)
    hits = list(response.hits)
    more = len(hits) > per_page
    hits = hits[:per_page]
    if more:
        next_cursor = encode_cursor([pit_id, list(hits[-1].meta.sort)])
    else:
        next_cursor = None
        close_pit(pit_id)
    return response.hits.total.value, [as_link(h) for h in hits], next_cursor


def link_type_id(relationship_id):
    """The /link-types id of a stored relationship id (oxjob #2481): .../relationships/citation ->
    .../link-types/citation."""
    if not relationship_id:
        return relationship_id
    return URL + "link-types/" + relationship_id.rstrip("/").split("/")[-1]


def as_link(hit):
    return {"origin": hit.origin, "target": hit.target, "relationship": hit.relationship,
            "link_type": link_type_id(hit.relationship)}


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
