"""
OQL Parser — thin prod-facing wrapper around the OQL engine.

`parse_oql_to_oqo()` delegates to the single OQL engine (`oql_lang.py`, promoted
from the v2 oracle in #376) and adapts its `OQLError` to the `OQLParseError`
shape that `views.py` consumes. The old split-based `OQLParser` class lived here
until #363; it is gone — the engine is the only parser.

See docs/oql-spec.md for the full specification.
"""

from typing import Optional, List
from dataclasses import dataclass

from query_translation.oqo import OQO
from query_translation.oql_lang import parse as _engine_parse, OQLError as _OQLError


@dataclass
class ParseError:
    """Represents a parsing error."""
    message: str
    position: Optional[int] = None
    context: Optional[str] = None


class OQLParseError(Exception):
    """Raised when OQL parsing fails."""
    def __init__(self, message: str, errors: Optional[List[ParseError]] = None):
        super().__init__(message)
        self.errors = errors or []


def parse_oql_to_oqo(oql: str) -> OQO:
    """
    Parse an OQL string into an OQO object.

    As of oxjob #376 (Phase 1) this delegates to the single OQL engine
    (`query_translation/oql_lang.py`, promoted from the v2 conformance oracle).
    The legacy split-based `OQLParser` class that used to live in this module —
    including its superseded name-first `Display Name [id]` bracket form — was
    removed (#363); the engine now treats `[...]` as an ignored annotation in the
    id-first `id [Display Name]` form. The engine's named `OQLError` (code +
    message + fix-it + position) is translated into the prod-facing
    `OQLParseError` shape that `views.py:_oql_parse_error_response` consumes
    (message + position + context).

    Args:
        oql: The OQL string to parse

    Returns:
        OQO object

    Raises:
        OQLParseError: If parsing fails
    """
    try:
        return _engine_parse(oql)
    except _OQLError as e:
        message = f"{e.message}  Fix: {e.fixit}" if e.fixit else e.message
        perr = ParseError(
            message=message,
            position=e.position,
            context=_error_context(oql, e.position),
        )
        raise OQLParseError(message, errors=[perr]) from e


def _error_context(oql: str, position: Optional[int], window: int = 24) -> Optional[str]:
    """A short substring of the query around `position`, for error display.

    Mirrors the (always-None) old behavior when there's no position; otherwise a
    +/- `window`-char snippet so the client can point at the offending text.
    """
    if position is None or not oql:
        return None
    start = max(0, position - window)
    end = min(len(oql), position + window)
    snippet = oql[start:end]
    return ("…" if start > 0 else "") + snippet + ("…" if end < len(oql) else "")
