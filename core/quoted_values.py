"""Double quotes in a non-search filter value (oxjob #2140).

Quotes group a value's spaces and commas into one value (`geo.region:"New York"` is one region,
not New York AND York); they never protect a `|`, which always separates OR operands. So a value
quoted whole keeps its long-standing meaning (`"a b|c d"` = OR of `a b` and `c d`, #363), and an
OR list may quote each operand (`"New York"|California`, `doi:"10.1/a"|"10.1/b"`), as the docs
tell users to. Before #2140 the quotes of such operands stayed in the value, so each quoted operand
matched nothing: the DOI list answered 0 and the region list answered California alone.

Search filters (`*.search*`) are not read here: their quotes mean a phrase.
Used by core/filter.py (the filter door) and query_translation/url_parser.py (the OQL echo).
"""


def _unquote_operand(operand):
    """`"a b"` -> `a b`, `!"a b"` -> `!a b`; anything else unchanged."""
    neg = ""
    if operand.startswith("!"):
        neg, operand = "!", operand[1:]
    if len(operand) >= 2 and operand.startswith('"') and operand.endswith('"') and '"' not in operand[1:-1]:
        operand = operand[1:-1]
    return neg + operand


def unquote_filter_value(value):
    """Return (value without its grouping quotes, is_quoted). `is_quoted` is True when the whole
    value was one quoted value (`"a b"` or `!"a b"`), so its spaces are literal rather than AND."""
    quoted_operands = "|" in value and '"' in value.strip('!"')  # `"a"|"b"`: not one quoted value
    if not quoted_operands:
        if len(value) >= 2 and value.startswith('"') and value.endswith('"'):
            return value[1:-1], True
        # The GUI negates a quoted value outside the quotes (`!"a b"`): same value as `"!a b"`
        # (#1463 follow-up, from #1473).
        if len(value) >= 3 and value.startswith('!"') and value.endswith('"'):
            return "!" + value[2:-1], True
        return value, False
    return "|".join(_unquote_operand(op) for op in value.split("|")), False
