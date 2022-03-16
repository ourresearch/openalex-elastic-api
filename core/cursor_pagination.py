import base64
import binascii
import json

from core.exceptions import APIPaginationError


def encode_cursor(cursor):
    cursor_json = json.dumps(str(cursor)).encode()
    return base64.b64encode(cursor_json).decode()


def decode_cursor(encoded_cursor):
    try:
        decoded_cursor = base64.b64decode(encoded_cursor)
        cursor_utf8 = decoded_cursor.decode("utf8")
        cursor_str = cursor_utf8.replace('"', "").replace("'", '"')
        cursor_json = json.loads(cursor_str)
    except (binascii.Error, json.decoder.JSONDecodeError):
        raise APIPaginationError("Invalid cursor value")
    return list(cursor_json)


def get_cursor(response):
    next_cursor = None
    hits = response["hits"]["hits"]
    last_record = hits[-1] if hits else None
    if last_record and "sort" in last_record:
        next_cursor = last_record["sort"]
    return next_cursor
