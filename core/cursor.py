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

    try:
        decoded_cursor = base64.b64decode(encoded_cursor)
        cursor_utf8 = decoded_cursor.decode("utf8")
        cursor_str = cursor_utf8.replace('"', "").replace("'", '"')

        if return_json:
            return list(json.loads(cursor_str))
        return cursor_str

    except (json.decoder.JSONDecodeError, ValueError):
        raise APIPaginationError("Invalid cursor value")


def get_cursor(response):
    next_cursor = None
    hits = response["hits"]["hits"]
    last_record = hits[-1] if hits else None
    if last_record and "sort" in last_record:
        next_cursor = last_record["sort"]
    return next_cursor


def get_next_cursor(params, response):
    if params.get("group_by"):
        elastic_cursor = get_group_by_after_key(params["group_by"], response)
    else:
        elastic_cursor = get_cursor(response)
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
