"""ES rejecting the user's search text answers a JSON 400 that says what to fix, not an HTML
500 (oxjob #1889). Live before: 157,671 HTTP 500s a week on openalex-search-api, nearly all
query-parse errors (token_mgr_error 119,470 lines, parse_exception 29,172).

app.py's handler is `if not is_user_query_error(err): raise err`, then a 400 with
user_query_error_message(err); these tests pin both functions without booting the app.
"""
import os
import sys

import pytest
from elastic_transport import ApiResponseMeta, HttpHeaders
from elasticsearch import BadRequestError, NotFoundError

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from core.user_query_errors import is_user_query_error, user_query_error_message  # noqa: E402


def _es_error(reason, cls=BadRequestError, status=400):
    meta = ApiResponseMeta(status=status, http_version="1.1", headers=HttpHeaders(), duration=0.0, node=None)
    body = {
        "error": {
            "root_cause": [{"type": "query_shard_exception", "reason": reason}],
            "type": "search_phase_execution_exception",
            "reason": "all shards failed",
        },
        "status": status,
    }
    return cls(message="search_phase_execution_exception", meta=meta, body=body)


@pytest.mark.parametrize("reason", [
    "Failed to parse query [cancer AND OR research]",
    "token_mgr_error: Lexical error at line 1, column 7173.  Encountered: <EOF> (in lexical state 2)",
    "parse_exception: Cannot parse 'a AND (OR b)'",
    "Valid edit distances are [0, 1, 2] but was [1952]",
    "too_many_clauses: maxClauseCount is set to 4096",
])
def test_user_query_errors_are_recognised(reason):
    assert is_user_query_error(_es_error(reason))


@pytest.mark.parametrize("err", [
    _es_error("No mapping found for [no_such_field] in order to sort on"),  # our bug: stays a 500
    _es_error("Failed to parse query [x]", cls=NotFoundError, status=404),   # not a 400
    ValueError("Failed to parse query"),
])
def test_other_errors_stay_errors(err):
    assert not is_user_query_error(err)


def test_messages_say_what_to_fix():
    assert "partner" in user_query_error_message(_es_error("Failed to parse query [a AND OR b]"))
    assert "fewer OR" in user_query_error_message(_es_error("too_many_clauses: maxClauseCount is set to 4096"))
    assert "0, 1 or 2" in user_query_error_message(_es_error("Valid edit distances are [0, 1, 2] but was [1952]"))
