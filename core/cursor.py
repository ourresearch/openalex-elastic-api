import ast
import base64
import json

from elasticsearch_dsl import AttrDict

import settings
from core.exceptions import APIPaginationError
from core.group_by.utils import parse_group_by, get_bucket_keys


def encode_cursor(cursor):
    # JSON, not Python repr. str(cursor) + quote-stripping broke on apostrophes
    # ("O'Brien", "Alzheimer's") and embedded quotes in search_after / after_key.
    if not isinstance(cursor, (str, int, float, bool, type(None), list, dict)):
        cursor = list(cursor)
    return base64.b64encode(json.dumps(cursor).encode()).decode()


def _decode_legacy_list_repr(payload):
    """Parse payloads from the old encoder (`json.dumps(str(list))`)."""
    return ast.literal_eval(payload)


def decode_cursor(encoded_cursor, return_json=True):
    if encoded_cursor == "null" or encoded_cursor.lower() == "none":
        raise APIPaginationError("Cursor is null. Likely reached end of results.")

    try:
        payload = json.loads(base64.b64decode(encoded_cursor).decode("utf8"))
    except (json.decoder.JSONDecodeError, ValueError, UnicodeDecodeError):
        raise APIPaginationError("Invalid cursor value")

    if return_json:
        if isinstance(payload, list):
            return payload
        if isinstance(payload, str):
            try:
                parsed = _decode_legacy_list_repr(payload)
            except (json.decoder.JSONDecodeError, ValueError):
                raise APIPaginationError("Invalid cursor value")
            if isinstance(parsed, list):
                return parsed
        raise APIPaginationError("Invalid cursor value")

    return payload


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
