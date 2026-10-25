"""Cursor round trips (oxjob #687, ZD 6418 / 4515): a sort value with an
apostrophe or a quote, or a True/False sort value, made the next page 400
"Invalid cursor value"."""
import base64

import pytest

from core.cursor import decode_cursor, decode_group_by_cursor, encode_cursor
from core.exceptions import APIPaginationError

# The cursor the API handed out on 2026-10-25 for page 21 of ZD 6418's search,
# sorted by display_name, and then rejected.
LIVE_CURSOR = ("IltcInZpb2xlbnQgYWN0cyBhbmQgdmlvbGVudGl6YXRpb246IGFzc2Vzc2luZywgYXBwbHlpbmcsIGFuZCBkZXZlbG9waW5n"
               "IGxvbm5pZSBhdGhlbnMnIHRoZW9yaWVzXCIsIDk2LjAsIDE0LCAnaHR0cHM6Ly9vcGVuYWxleC5vcmcvVzIwNTU2NDE1OTYnXSI=")


def test_the_cursor_that_failed_in_production_decodes():
    assert decode_cursor(LIVE_CURSOR) == [
        "violent acts and violentization: assessing, applying, and developing lonnie athens' theories",
        96.0, 14, "https://openalex.org/W2055641596"]


@pytest.mark.parametrize("values", [
    ["the relationship between obesity and depression", 12.5, 3, "https://openalex.org/W1"],
    ["o'brien, patrick", "https://openalex.org/A5000000001"],
    ['a "quoted" title', "https://openalex.org/W2"],
    ["both ' and \" in one", 1],
    ["children's health", None, -9223372036854775808],
    [True, 2020, "https://openalex.org/W3"],
    ["back\\slash and unicodé ünïcode", 0.0],
    ["-Infinity", "https://openalex.org/W4"],
])
def test_sort_values_round_trip(values):
    assert decode_cursor(encode_cursor(values)) == values


@pytest.mark.parametrize("key", ["https://openalex.org/I136199984", "children's health", 'say "hi"', "2020"])
def test_group_by_keys_round_trip(key):
    assert decode_group_by_cursor(encode_cursor(key)).sub_key == key


def test_group_by_none_key_keeps_its_old_meaning():
    assert decode_group_by_cursor(encode_cursor(None)).sub_key == "null"


@pytest.mark.parametrize("bad", [
    "abc", "not base64 !!", base64.b64encode(b'{"a": 1}').decode(),
    base64.b64encode(b'"__import__(\'os\')"').decode(), base64.b64encode(b'"42"').decode(),
])
def test_garbage_is_an_invalid_cursor(bad):
    with pytest.raises(APIPaginationError):
        decode_cursor(bad)


@pytest.mark.parametrize("null", ["null", "None", "none"])
def test_null_cursor_says_results_ended(null):
    with pytest.raises(APIPaginationError, match="null"):
        decode_cursor(null)


def test_a_plain_json_list_still_decodes():
    assert decode_cursor(base64.b64encode(b'[1, "x", null]').decode()) == [1, "x", None]
