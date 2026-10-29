"""Elasticsearch rejecting the user's own search text (oxjob #1889).

core/search.py cleans search text before it reaches query_string, so these are rare. What
still gets through (`a AND OR b`, `1920~1952`, a wildcard that expands too far) is the
user's to fix: app.py answers a JSON 400 with the message below, and sentry_setup.py keeps
it out of Sentry. Before, the API answered HTML 500 (~150K a week, mostly clients retrying
the same query).
"""
from elasticsearch import BadRequestError

_TOO_BIG = (
    "Your search expands to more terms than can be run at once. Use fewer OR terms, "
    "or a longer start before each * wildcard."
)
_EDIT_DISTANCE = (
    "A ~ after a word sets how many letters may differ, and it must be 0, 1 or 2 "
    "(cancer~1). For words near each other, quote them: \"heart failure\"~5."
)
_WHOLE_KEYWORDS = (
    "keyword.search matches whole keywords, so a * or ? inside quotes can't run there. "
    "Drop the quotes (canc*), or search titles and abstracts with title_and_abstract.search."
)
_OUT_OF_RANGE = "A number in your filter is too large for that field. Use a smaller number."
_UNREADABLE = (
    "Your search could not be read. Check that each quote and parenthesis has a "
    "partner, and that AND, OR and NOT each sit between two search terms."
)

# Text Elasticsearch puts in a 400 when the user's query can't be parsed or is too big,
# and what to tell them. First match wins, so the specific rows come first.
_USER_QUERY_ERRORS = (
    ("too_many_clauses", _TOO_BIG),
    ("too_many_nested_clauses", _TOO_BIG),
    ("maxClauseCount", _TOO_BIG),
    ("too_complex_to_determinize", _TOO_BIG),
    ("Valid edit distances are", _EDIT_DISTANCE),  # a title's "1920~1952" read as fuzzy distance 1952
    ("fuzziness cannot be", _EDIT_DISTANCE),  # "100~MHz": what follows a ~ read as a fuzziness
    # keyword.search:"canc* research": a quoted wildcard phrase becomes an intervals query, which
    # needs a text field; keywords.display_name is a keyword field (oxjob #1900).
    ("Can only use interval queries on text fields", _WHOLE_KEYWORDS),
    # publication_year:>99999999999999999999: a finite number past the field's integer range (oxjob #1913)
    ("is out of range for", _OUT_OF_RANGE),
    ("token_mgr_error", _UNREADABLE),
    ("Failed to parse query", _UNREADABLE),
    ("Cannot parse", _UNREADABLE),
    ("parse_exception", _UNREADABLE),
)


def user_query_error_message(exc):
    """What to tell the user when Elasticsearch rejected their own search text; None
    for any other error (ours to fix)."""
    if not isinstance(exc, BadRequestError):
        return None
    text = f"{exc} {getattr(exc, 'body', '')}"
    return next((message for marker, message in _USER_QUERY_ERRORS if marker in text), None)


def is_user_query_error(exc):
    return user_query_error_message(exc) is not None
