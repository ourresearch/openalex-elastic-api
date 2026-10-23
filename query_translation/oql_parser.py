"""
OQL Parser — thin prod-facing wrapper around the OQL engine.

`parse_oql_to_oqo()` delegates to the single OQL engine (`oql_lang.py`, promoted
from the v2 oracle in #376) and adapts its `OQLError` to the `OQLParseError`
shape that `views.py` consumes. The old split-based `OQLParser` class lived here
until #363; it is gone — the engine is the only parser.

See docs/oql-spec.md for the full specification.
"""

import re
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
        return parse_either(oql)
    except _OQLError as e:
        core_error = getattr(e, "core_error", None)
        if core_error is not None:
            msg, fix = core_reason(core_error)
            message = f"{msg}  Fix: {fix}" if fix else msg
            raise OQLParseError(message, errors=[ParseError(message=message, position=None,
                                                            context=None)]) from e
        raise _parse_error(oql, e) from e


def parse_either(oql: str) -> OQO:
    """An OQL core v3 sentence or today's grammar (oxjob #1555): the one reading every
    surface shares (execute, /query, the editor's /validate). Raises the engine's OQLError
    (code, fix-it, position); when the text started as a core sentence that neither
    grammar reads, the error's `core_error` carries core's reason."""
    from query_translation.oql_core import NotCore, core_first, parse_core
    core_error = None
    if core_first(oql):
        # `get the ...` (a table or a number); a search or `where` part of a core
        # sentence that fails raises the engine's own OQLError
        try:
            return parse_core(oql, _collection_type)
        except NotCore as ce:
            core_error = ce          # reported if today's grammar can't read it either
    try:
        return _engine_parse(oql)
    except _OQLError as e:
        if core_error is None and oql.lstrip()[:4].lower() == "get ":
            # a core `get` sentence today's grammar refuses (`get [UBC]'s articles since 2020`)
            try:
                return parse_core(oql, _collection_type)
            except (NotCore, _OQLError) as ce:
                if _meant_as_a_sentence(oql, e):
                    core_error = ce
        e.core_error = core_error
        raise


_HEAD = re.compile(r"\s*get\s+\S+\s*", re.I)


def _meant_as_a_sentence(oql: str, e) -> bool:
    """Today's grammar stopped right after `get <word>` (`get works about ...`), so the
    text was written as a sentence and core's reason is the one to show (#1589's recheck,
    2026-10-23: the old error pointed at the old form)."""
    head = _HEAD.match(oql)
    # at the word after the noun; an error AT the noun (`get workz ...`) keeps today's reason
    return head is not None and e.position is not None and head.end() - 1 <= e.position <= head.end()


def core_reason(core_error):
    """(message, fixit) for a sentence's error: core's NotCore, or an OQLError from the
    `where` part (its position is in the inner text, so it is dropped)."""
    if isinstance(core_error, _OQLError):
        return core_error.message, core_error.fixit
    return str(core_error).split("  Fix: ", 1)[0], getattr(core_error, "fix", "")


def _parse_error(oql: str, e) -> "OQLParseError":
    """The prod-facing error for the engine's OQLError (message + fix-it + position)."""
    message = f"{e.message}  Fix: {e.fixit}" if e.fixit else e.message
    perr = ParseError(message=message, position=e.position,
                      context=_error_context(oql, e.position))
    return OQLParseError(message, errors=[perr])


def _collection_type(collection_id: str) -> Optional[str]:
    """A collection's entity type, for `works in the collection [X]` (oxjob #1555): the
    same `GET /collections/{id}` and per-request memo as its name in the echo."""
    try:
        from core.collection_resolver import collection_entity_type
        return collection_entity_type(collection_id)
    except Exception:  # noqa: BLE001 (no users-api here: read it as a works collection)
        return None


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
