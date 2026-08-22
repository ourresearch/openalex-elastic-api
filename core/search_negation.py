"""Refuse whole-query negation in search values (oxjob #857).

A search value that *begins* with `NOT` (`NOT dog`, `(NOT dog)`, `NOT "dog"`)
was silently mis-executed: `is_boolean_search()` only recognises ` NOT `
with a space on BOTH sides, so a leading `NOT` never reached the
`query_string` branch, fell through to a plain `match`, and the English
analyzer dropped `not` as a stopword — `search.title=NOT dog` returned
exactly the `dog` set. On the no-stem `.exact` columns `not` is a real
token, so the same value matched works containing both words (a third
wrong answer).

Whole-query negation is deliberately NOT supported on any REST search door
(it is the same question as the long-standing `!`-on-search 400, and a
match-everything-but-X search is never what a search box means), so we
reject it loudly instead of answering the opposite question. `NOT` between
terms (`dog NOT cat`) is untouched. A leading `-` is NOT treated as a
negation operator: #633's docs-aligned allowlist makes undocumented Lucene
modifiers literal text, and the analyzer simply drops the hyphen.
"""
import re

from core.exceptions import APIQueryParamsError

# Optional whitespace / opening parens, then the uppercase operator as a
# whole word (so `NOTHING`, `notable`, and the quoted phrase `"NOT dog"`
# all pass). Only the documented uppercase spelling is an operator.
_LEADING_NOT_RE = re.compile(r'^[\s(]*NOT\b')


def has_leading_not(value):
    """True if `value` starts with the `NOT` operator (whole-query negation)."""
    return bool(value) and _LEADING_NOT_RE.match(value) is not None


def validate_no_leading_not(value):
    """Raise the user-facing 400 for a search value that begins with `NOT`."""
    if has_leading_not(value):
        raise APIQueryParamsError(
            "Search values cannot begin with NOT: a search needs at least one "
            "positive term to match, e.g. 'cat NOT dog'. "
            f"Problem value: {value}"
        )
