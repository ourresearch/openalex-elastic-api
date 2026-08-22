"""Whole-query negation in search values (oxjob #857).

A search value that *begins* with `NOT` (`NOT dog`, `NOT "dog food"`,
`NOT (dog OR cat)`) used to be silently mis-executed: `is_boolean_search()`
only recognised ` NOT ` with a space on BOTH sides, so a leading `NOT`
never reached the `query_string` branch, fell through to a plain `match`,
and the English analyzer dropped `not` as a stopword — `search.title=NOT dog`
returned exactly the `dog` set. On the no-stem `.exact` columns `not` is a
real token, so the same value matched works containing both words.

Now `NOT <one operand>` is the exact complement of `<one operand>` on every
door: the engine builds the positive query exactly as it would without the
`NOT` and wraps it in `bool.must_not`. Wrapping (rather than handing `NOT x`
to `query_string`) matters on the multi-field doors, which OR per-field
clauses in some branches — negation distributes over that OR as
"not in title OR not in abstract", which excludes only works matching in
BOTH fields. A leading `NOT` with more than one operand after it
(`NOT dog cat`, `NOT dog AND cat`) keeps Lucene's usual modifier semantics
(`-dog +cat`, i.e. "cat without dog"), the same as `dog NOT cat` today.

Only the documented uppercase spelling is the operator: `not dog` is two
words, and a leading `-` is literal text per #633's docs-aligned allowlist.
"""
import re

# Optional whitespace, then the uppercase operator as a whole word (so
# `NOTHING`, `notable`, and the quoted phrase `"NOT dog"` are not matches).
_LEADING_NOT_RE = re.compile(r"^\s*NOT\b\s*(.*)$", re.S)
_QUOTED_OPERAND_RE = re.compile(r'^"[^"]*"(~\d+)?$')


def has_leading_not(value):
    """True if `value` starts with the `NOT` operator and something follows it."""
    return split_leading_not(value) is not None


def split_leading_not(value):
    """`NOT <rest>` -> `<rest>` (stripped); None if there is no leading NOT
    or nothing follows it (a bare `NOT` is left to the existing paths)."""
    if not value:
        return None
    m = _LEADING_NOT_RE.match(value)
    if not m:
        return None
    rest = m.group(1).strip()
    return rest or None


def _is_wrapped_in_parens(s):
    """True if the first `(` closes at the very end (one enclosing group)."""
    if len(s) < 2 or s[0] != "(" or s[-1] != ")":
        return False
    depth = 0
    in_quotes = False
    for i, ch in enumerate(s):
        if ch == '"':
            in_quotes = not in_quotes
        elif not in_quotes:
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth == 0:
                    return i == len(s) - 1
    return False


def is_single_operand(s):
    """One search operand: a bare token, a quoted phrase (optionally `~N`),
    or one enclosing paren group."""
    s = s.strip()
    if not s:
        return False
    if _QUOTED_OPERAND_RE.match(s):
        return True
    if _is_wrapped_in_parens(s):
        return True
    return not any(ch.isspace() for ch in s)


def whole_query_negation_operand(value):
    """If `value` is `NOT <one operand>`, return that operand (the positive
    query to complement); else None. Strips one enclosing paren pair first
    so `(NOT dog)` behaves like `NOT dog`."""
    v = (value or "").strip()
    if _is_wrapped_in_parens(v):
        inner = v[1:-1].strip()
        if split_leading_not(inner) is not None:
            v = inner
    rest = split_leading_not(v)
    if rest is None or not is_single_operand(rest):
        return None
    return rest
