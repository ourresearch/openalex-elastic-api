"""Cursor encode/decode must round-trip sort values that contain quotes.

`core/cursor.py` used `json.dumps(str(cursor))` plus a `.replace('"', "")` /
`.replace("'", '"')` scrub. That works for numeric `search_after` tuples, but
any sort value with an apostrophe (paper titles like "Alzheimer's", author
names like "O'Brien") or an embedded double quote either 400s as an invalid
cursor or silently mangles the group-by `after_key`.
"""
import base64
import json

import pytest

from core.cursor import decode_cursor, decode_group_by_cursor, encode_cursor
from core.exceptions import APIPaginationError


def _legacy_encode(cursor):
    """The pre-fix encoder: JSON-wrap Python's `str(cursor)`."""
    return base64.b64encode(json.dumps(str(cursor)).encode()).decode()


def test_list_cursor_roundtrip_with_apostrophe():
    original = [1847, "O'Brien"]
    assert decode_cursor(encode_cursor(original)) == original


def test_list_cursor_roundtrip_with_embedded_quotes():
    original = [99, 'He said "hello"']
    assert decode_cursor(encode_cursor(original)) == original


def test_list_cursor_roundtrip_with_none():
    original = [None, "https://openalex.org/W123"]
    assert decode_cursor(encode_cursor(original)) == original


def test_list_cursor_roundtrip_plain_openalex_id():
    original = [12, "https://openalex.org/W2741809807"]
    assert decode_cursor(encode_cursor(original)) == original


def test_group_by_cursor_roundtrip_with_apostrophe():
    key = "Cote d'Ivoire"
    decoded = decode_cursor(encode_cursor(key), return_json=False)
    assert decoded == key
    assert decode_group_by_cursor(encode_cursor(key)).sub_key == key


def test_group_by_cursor_roundtrip_unicode():
    key = "Côte d'Ivoire"
    assert decode_cursor(encode_cursor(key), return_json=False) == key


def test_legacy_numeric_list_cursor_still_decodes():
    """Cursors already in the wild must keep working."""
    legacy = _legacy_encode([12, "https://openalex.org/W2741809807"])
    assert decode_cursor(legacy) == [12, "https://openalex.org/W2741809807"]


def test_legacy_list_cursor_with_apostrophe_still_decodes():
    original = [1847, "O'Brien"]
    assert decode_cursor(_legacy_encode(original)) == original


def test_legacy_list_cursor_with_embedded_quotes_still_decodes():
    original = [99, 'He said "hello"']
    assert decode_cursor(_legacy_encode(original)) == original


def test_legacy_list_cursor_with_none_still_decodes():
    original = [None, "https://openalex.org/W123"]
    assert decode_cursor(_legacy_encode(original)) == original


def test_legacy_plain_group_by_key_still_decodes():
    legacy = _legacy_encode("Harvard University")
    assert decode_cursor(legacy, return_json=False) == "Harvard University"


def test_null_cursor_raises():
    with pytest.raises(APIPaginationError):
        decode_cursor("null")


def test_invalid_cursor_raises():
    with pytest.raises(APIPaginationError):
        decode_cursor("not-valid-base64-$$$")
