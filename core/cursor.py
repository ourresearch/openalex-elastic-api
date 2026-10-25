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


def get_cursor(response, per_page):
    hits = response["hits"]["hits"]
    if len(hits) < per_page:
        return None
    last_record = hits[-1]
    if "sort" not in last_record:
        return None
    return last_record["sort"]


def get_next_cursor(params, response):
    if params.get("group_by"):
        elastic_cursor = get_group_by_after_key(params["group_by"], response)
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


def get_group_by_after_key(group_by, response):
    group_by, _ = parse_group_by(group_by)
    bucket_keys = get_bucket_keys(group_by)
    if (
        bucket_keys["default"] not in response.aggregations
        or "after_key" not in response.aggregations[bucket_keys["default"]]
    ):
        return None
    return response.aggregations[bucket_keys["default"]].after_key["sub_key"]


def decode_group_by_cursor(cursor):
    decoded_cursor = decode_cursor(cursor, return_json=False)
    after_key = AttrDict({"sub_key": decoded_cursor})
    return after_key
