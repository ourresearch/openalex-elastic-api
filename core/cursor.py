import base64
import json

from core.exceptions import APIPaginationError


def encode_cursor(cursor):
    cursor_json = json.dumps(str(cursor)).encode()
    return base64.b64encode(cursor_json).decode()


def decode_cursor(encoded_cursor):
    if encoded_cursor == "null" or encoded_cursor.lower() == "none":
        raise APIPaginationError("Cursor is null. Likely reached end of results.")
    try:
        decoded_cursor = base64.b64decode(encoded_cursor)
        cursor_utf8 = decoded_cursor.decode("utf8")
        cursor_str = cursor_utf8.replace('"', "").replace("'", '"')
        cursor_json = json.loads(cursor_str)
    except (json.decoder.JSONDecodeError, ValueError):
        raise APIPaginationError("Invalid cursor value")
    return list(cursor_json)


def get_cursor(response):
    next_cursor = None
    hits = response["hits"]["hits"]
    last_record = hits[-1] if hits else None
    if last_record and "sort" in last_record:
        next_cursor = last_record["sort"]
    return next_cursor


def get_next_cursor(response):
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
