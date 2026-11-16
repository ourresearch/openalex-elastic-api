import ast
import base64
import json

from elasticsearch_dsl import AttrDict

import settings
from core.exceptions import APIPaginationError
from core.group_by.utils import parse_group_by, get_bucket_keys


def encode_cursor(cursor):
    cursor_json = json.dumps(str(cursor)).encode()
    return base64.b64encode(cursor_json).decode()


def decode_cursor(encoded_cursor, return_json=True):
    if encoded_cursor == "null" or encoded_cursor.lower() == "none":
        raise APIPaginationError("Cursor is null. Likely reached end of results.")

    # encode_cursor writes json.dumps(str(value)): a JSON string holding a Python
    # literal (the sort values' list repr, or a group-by bucket key). Read it back
    # as one. Swapping quote characters to make JSON broke on any value with an
    # apostrophe or a quote in it ("...Lonnie Athens' Theories" under
    # sort=display_name, O'Brien, a bucket key like "children's health") and on
    # True/False sort values (oxjob #687, ZD 6418 / 4515).
    try:
        text = json.loads(base64.b64decode(encoded_cursor).decode("utf8"))
        if return_json and isinstance(text, list):  # plain JSON, as the old decode also took
            return text
        if not isinstance(text, str):
            raise ValueError("not an encoded cursor")
        if not return_json:
            return "null" if text == "None" else text
        values = ast.literal_eval(text)
        if not isinstance(values, (list, tuple)):
            raise ValueError("not a list of sort values")
        return list(values)

    except (ValueError, SyntaxError, TypeError, MemoryError, RecursionError):
        # (binascii.Error, UnicodeDecodeError and JSONDecodeError are ValueErrors)
        raise APIPaginationError("Invalid cursor value")


# A cursor page asks Elasticsearch for one hit more than it shows (oxjob #1029,
# ZD 2081 / 4314 / 4563). Without it a page that came back exactly full could not
# tell "more behind this" from "that was the last one", so the last page of a walk
# whose count is a multiple of per-page handed out a next_cursor to an empty page.
MORE_AFTER_PAGE = "_more_after_this_page"


def peek_one_more(params):
    """1 when this request is a cursor page that should look one hit past its end, else 0."""
    if params.get("cursor") and not params.get("group_by") and not params.get("sample"):
        return 1
    return 0


def drop_peeked_hit(response, per_page):
    """Remove the look-ahead hit before anything reads the hits, and remember whether it was there.

    Call right after execute(): elasticsearch_dsl builds response.hits from the raw list lazily."""
    raw = response._d_["hits"]
    more = len(raw["hits"]) > per_page
    if more:
        raw["hits"] = raw["hits"][:per_page]
    if more or not response._d_.get("timed_out"):
        # A page cut short by the 5 s soft timeout (oxjob #521) can't say nothing follows it: leave the flag
        # unset there, so get_cursor keeps the old rule and a full page still hands out its cursor.
        # AttrDict's own __setattr__ would write the flag into the hit data, so set it on the object.
        object.__setattr__(response, MORE_AFTER_PAGE, more)
    return response


def get_cursor(response, per_page):
    hits = response["hits"]["hits"]
    if len(hits) < per_page:
        return None
    if getattr(response, MORE_AFTER_PAGE, None) is False:
        return None  # a full page, and the look-ahead found nothing after it: the walk is done
    last_record = hits[-1]
    if "sort" not in last_record:
        return None
    return last_record["sort"]


def get_next_cursor(params, response):
    if params.get("group_by"):
        elastic_cursor = get_group_by_after_key(params["group_by"], response, params.get("per_page"))
    else:
        elastic_cursor = get_cursor(response, params["per_page"])
    next_cursor = encode_cursor(elastic_cursor) if elastic_cursor else None
    return next_cursor


def handle_cursor(cursor, page, s):
    if cursor and page != 1:
        raise APIPaginationError("Cannot use page parameter with cursor.")
    if cursor and cursor != "*":
        decoded_cursor = decode_cursor(cursor)
        s = s.extra(search_after=decoded_cursor)
    return s


def get_group_by_after_key(group_by, response, per_page=None):
    group_by, _ = parse_group_by(group_by)
    bucket_keys = get_bucket_keys(group_by)
    if (
        bucket_keys["default"] not in response.aggregations
        or "after_key" not in response.aggregations[bucket_keys["default"]]
    ):
        return None
    agg = response.aggregations[bucket_keys["default"]]
    # Elasticsearch gives a composite aggregation an after_key on its last, short page too, so every group-by
    # cursor walk ended with one call for an empty page (oxjob #1029; 16 Nov: institution.id, 196 groups on page
    # 635, then 0). The composite asks for per_page buckets: fewer means none follow, unless the 5 s soft
    # timeout (oxjob #521) cut the answer short.
    if per_page and len(agg.buckets) < per_page and not response_timed_out(response):
        return None
    return agg.after_key["sub_key"]


def response_timed_out(response):
    try:
        return bool(response["timed_out"])
    except (KeyError, TypeError):
        return False


def decode_group_by_cursor(cursor):
    decoded_cursor = decode_cursor(cursor, return_json=False)
    after_key = AttrDict({"sub_key": decoded_cursor})
    return after_key
