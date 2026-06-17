"""
Shared OQL/OQO diagnostics vocabulary — the one registry of every diagnostic the
OQL stack can emit (oxjob #363; charter decision 5: "codes are the language-agnostic
contract, prose localizes").

Before this module the diagnostic vocabulary was scattered: ~30 ``OQL_*`` codes were
constructed inline at their raise sites in ``oql_lang.py`` (the parser), the OQO
validator (``validator.py``) emitted a *separate* ``invalid_*`` namespace with no
fix-it and no position, and the editor walker (``oql_context.py``) re-derived a few
more. Three surfaces, two vocabularies, no single place a consumer (the #357 editor,
the #344 NL eval, a future client) could read "what are all the codes, and what does
each mean?".

This module is that single place. It enumerates **every** code — both the parser/lexer
``OQL_*`` layer and the OQO-validator ``invalid_*`` layer — each with a stable
``severity``, a one-line human ``summary``, and a ``default_fixit`` used when a raise
site doesn't supply richer per-instance prose. The error/hint carriers (``OQLError``,
``OQLHint``) live here too so the vocabulary and the things that carry it can't drift.

Pure leaf module: standard library only, imports nothing from the rest of
``query_translation`` — so the Flask-free engine (``oql_lang``), the validator, and the
editor routes can all depend on it without an import cycle. ``oql_lang`` re-exports
``OQLError``/``OQLHint`` for backwards compatibility (``from ...oql_lang import OQLError``
still works, and ``oql_v2``'s ``import *`` still re-exports the engine).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional


# --- severities & layers ------------------------------------------------------
ERROR = "error"
WARNING = "warning"

# Which stage of the OQL pipeline raises the code. ``parse`` codes carry a byte
# position into the OQL string; ``validate`` codes carry an OQO JSON-path location.
PARSE = "parse"
VALIDATE = "validate"


# --- carriers -----------------------------------------------------------------
class OQLError(Exception):
    """A fatal parse/lex diagnostic: a named ``code`` plus human ``message``, an
    actionable ``fixit``, and the byte ``position`` in the OQL string (when known).

    The parser is fail-fast — it raises the first of these it hits. The code is the
    stable contract (registered in ``DIAGNOSTICS``); the message/fixit prose localizes.
    """

    def __init__(self, code: str, message: str, fixit: str = "",
                 position: Optional[int] = None):
        self.code = code
        self.message = message
        self.fixit = fixit
        self.position = position
        super().__init__(f"[{code}] {message}" + (f"  Fix: {fixit}" if fixit else ""))


@dataclass
class OQLHint:
    """A non-fatal diagnostic: collected on the parse (in ``_Parser.hints``), never
    raised. Same ``code``/``message``/``fixit`` contract as ``OQLError``."""

    code: str
    message: str
    fixit: str = ""


# --- the registry -------------------------------------------------------------
@dataclass(frozen=True)
class DiagnosticSpec:
    """The stable, language-agnostic facts about a diagnostic code.

    ``summary`` is a short, instance-independent description of the code (for docs /
    the editor's "what does this mean" hover). ``default_fixit`` is the canonical
    remedy, used whenever a raise site / validation check doesn't supply a more
    specific one.
    """

    code: str
    severity: str
    layer: str
    summary: str
    default_fixit: str = ""


def _spec(code, severity, layer, summary, default_fixit=""):
    return DiagnosticSpec(code, severity, layer, summary, default_fixit)


# Every diagnostic the OQL stack can emit. PARSE codes are raised by the lexer/parser
# in oql_lang.py; VALIDATE codes are emitted by the OQO validator in validator.py.
# Keep this list in lockstep with those two modules — `test_diagnostics.py` asserts
# the registry and the raise sites agree (no code raised that isn't registered, and
# every registered PARSE/VALIDATE code carries a non-empty fix-it).
DIAGNOSTICS: Dict[str, DiagnosticSpec] = {
    s.code: s
    for s in [
        # -- lexer ----------------------------------------------------------------
        _spec("OQL_UNTERMINATED_STRING", ERROR, PARSE,
              "a double-quoted string was opened but never closed",
              'add a closing double-quote (")'),
        _spec("OQL_UNTERMINATED_ANNOTATION", ERROR, PARSE,
              "a [...] annotation was opened but never closed",
              "add a closing bracket (])"),
        # -- top-level structure --------------------------------------------------
        _spec("OQL_EMPTY", ERROR, PARSE,
              "the query (or a where-condition) is empty",
              'add a condition, e.g. "works where year >= 2020"'),
        _spec("OQL_MISSING_ENTITY", ERROR, PARSE,
              "the query does not start with an entity type",
              'start with an entity, e.g. "works where ..."'),
        _spec("OQL_UNKNOWN_ENTITY", ERROR, PARSE,
              "the leading word is not a known entity type",
              "use one of: works, authors, institutions, sources, ..."),
        _spec("OQL_TRAILING_TOKENS", ERROR, PARSE,
              "unexpected text after the query's clauses",
              "queries are: <entity> [where <conditions>] [sort by ...] "
              "[group by ...] [sample N] [return col1, col2]"),
        # -- boolean structure ----------------------------------------------------
        _spec("OQL_IMPLICIT_ADJACENCY", ERROR, PARSE,
              "two conditions sit side by side with no AND/OR between them",
              "insert an explicit AND or OR"),
        _spec("OQL_MIXED_BOOL_NEEDS_PARENS", ERROR, PARSE,
              "AND and OR are mixed at one grouping level (ambiguous)",
              'group explicitly, e.g. "a and (b or c)" or "(a and b) or c"'),
        _spec("OQL_UNBALANCED_PARENS", ERROR, PARSE,
              "a closing parenthesis is missing",
              "add a )"),
        # -- field / operator -----------------------------------------------------
        _spec("OQL_UNKNOWN_FIELD", ERROR, PARSE,
              "the field name is not in the properties registry",
              "check the field name against the properties registry"),
        _spec("OQL_MISSING_OPERATOR", ERROR, PARSE,
              "an operator is expected after the field",
              "add an operator, e.g. is / has / >="),
        _spec("OQL_BAD_OPERATOR_FOR_FIELD", ERROR, PARSE,
              "the operator does not fit the field's kind",
              'use an operator that matches the field (e.g. "has" for search, '
              '"is"/comparison for values)'),
        _spec("OQL_CONTAINS_RENAMED", ERROR, PARSE,
              "the `contains` operator was renamed to `has` (#363 decision 27)",
              "use `has`, e.g. title has machine learning"),
        _spec("OQL_UNKNOWN_BOOLEAN", ERROR, PARSE,
              'an "it\'s ..."/"it has ..." phrase names no known boolean property',
              'e.g. "it\'s open access", "it has a DOI"'),
        # -- values ---------------------------------------------------------------
        _spec("OQL_MISSING_VALUE", ERROR, PARSE,
              "a value is expected after the operator",
              "supply a value for the field"),
        _spec("OQL_MISSING_ENTITY_ID", ERROR, PARSE,
              "an entity ref has a [display name] but no authoritative ID",
              "put the OpenAlex ID first, e.g. institution is I136199984 [Harvard]"),
        _spec("OQL_BAD_NUMBER", ERROR, PARSE,
              "a numeric field was given a non-numeric value",
              "use a whole number, e.g. year is 2020"),
        _spec("OQL_BAD_DATE", ERROR, PARSE,
              "a date field was given a value that is not a full ISO date",
              "use YYYY-MM-DD, e.g. date is 2020-05-17"),
        _spec("OQL_RANGE_LITERAL_REMOVED", ERROR, PARSE,
              "the dash range literal (year is 2019-2023) was removed; "
              "write explicit endpoint clauses",
              "use the endpoints, e.g. year >= 2019 and year <= 2023"),
        _spec("OQL_BAD_COLLECTION_REF", ERROR, PARSE,
              '"is in collection" needs a collection id (col_…)',
              "e.g. work is in collection col_abc123"),
        _spec("OQL_UNDELIMITED_TERM_LIST", ERROR, PARSE,
              "two or more bare terms/values follow an operator without "
              "parentheses (a reserved word could be silently swallowed)",
              "wrap the terms in parentheses, e.g. has (a or b), "
              "or quote a phrase, e.g. has \"a b\""),
        _spec("OQL_LIST_KEYWORD_REMOVED", ERROR, PARSE,
              '"any of"/"all of"/"is in" value-list keywords were removed; '
              "lists are written with parentheses",
              "write it with parentheses, e.g. is (a or b) / has (a or b)"),
        _spec("OQL_COMMA_IN_GROUP", ERROR, PARSE,
              "a comma separates items in a (…) group (commas were removed)",
              "separate items with 'or'/'and', e.g. (a or b)"),
        # (OQL_BARE_NOT removed in decision 23 — `not` is now a bare prefix
        # keyword, so a bare `not foo` is valid, not an error.)
        _spec("OQL_BANG_NOT_SUPPORTED", ERROR, PARSE,
              "`!` is not an OQL operator — it is Web of Science / classic-URL "
              "syntax; OQL negates with not(…). (The compact `term!\"phrase\"` "
              "form is accepted only on the classic OXURL surface.)",
              'use not(…), e.g. (England and not("New England"))'),
        _spec("OQL_SEMANTIC_NEEDS_TEXT", ERROR, PARSE,
              '"is similar to" needs a quoted text passage',
              'e.g. abstract is similar to "..."'),
        # -- search: proximity & wildcards ----------------------------------------
        _spec("OQL_BAD_PROXIMITY", ERROR, PARSE,
              'malformed "within N words" proximity syntax',
              'e.g. title has "a b" within 5 words'),
        _spec("OQL_BINARY_PROXIMITY_NEEDS_PHRASES", ERROR, PARSE,
              "binary proximity requires exact-quoted phrases on both sides",
              'e.g. "machine learning" within 5 words of "health"'),
        _spec("OQL_PROXIMITY_NEEDS_PHRASE", ERROR, PARSE,
              "proximity needs a phrase (quoted or multi-word)",
              'quote the phrase, e.g. "climate change" within 5 words'),
        _spec("OQL_WILDCARD_IN_PROXIMITY", ERROR, PARSE,
              "wildcards are not allowed inside a proximity search",
              "remove the * / ? from the proximity phrase"),
        _spec("OQL_WILDCARD_NEEDS_EXACT", ERROR, PARSE,
              "a bare wildcard term needs exact (non-stemmed) matching",
              'quote it, or use "exactly", so the wildcard is not stemmed'),
        _spec("OQL_LEADING_WILDCARD", ERROR, PARSE,
              "a wildcard at the start of a term is not supported (too expensive)",
              "anchor the wildcard with leading characters, e.g. cycle*"),
        _spec("OQL_SHORT_WILDCARD_PREFIX", ERROR, PARSE,
              "a prefix wildcard needs at least 3 leading characters",
              "add characters before the *, e.g. abc*"),
        _spec("OQL_TOO_MANY_WILDCARDS", ERROR, PARSE,
              "too many wildcards in one phrase or proximity search",
              "remove a wildcard, or split into separate searches"),
        _spec("OQL_MULTI_WILDCARD_SHORT_PREFIX", ERROR, PARSE,
              "with two wildcards in one phrase, each needs a longer prefix",
              "use a longer prefix (e.g. abcd*) or drop a wildcard"),
        # -- directives -----------------------------------------------------------
        _spec("OQL_BAD_SORT", ERROR, PARSE,
              '"sort by" is missing a field name',
              "name a field to sort by, e.g. sort by cited_by_count desc"),
        _spec("OQL_BAD_SAMPLE", ERROR, PARSE,
              '"sample" is missing a positive integer',
              "give a count, e.g. sample 100"),
        _spec("OQL_BAD_RETURN", ERROR, PARSE,
              '"return" is missing a column name',
              "name a column to return, e.g. return id, title"),
        # -- generic catch-all (editor only; non-OQLError engine failures) --------
        _spec("OQL_PARSE_ERROR", ERROR, PARSE,
              "an unexpected parser failure",
              "simplify the query and try again"),

        # -- OQO validator (post-parse, against the live property catalog) --------
        _spec("invalid_entity", ERROR, VALIDATE,
              "the entity (get_rows) is not a queryable entity",
              "use a valid entity, e.g. works / authors / institutions"),
        _spec("invalid_column", ERROR, VALIDATE,
              "a referenced column is not a property of this entity",
              "check the column against /properties for this entity"),
        _spec("invalid_operator", ERROR, VALIDATE,
              "the operator is not a recognized OQO operator",
              "use a recognized operator (is / is not / has / >= …)"),
        _spec("invalid_operator_for_column", ERROR, VALIDATE,
              "the operator does not fit the column's type",
              "use an operator that matches the column's type"),
        _spec("invalid_value_type", ERROR, VALIDATE,
              "the value's type does not match the column's type",
              "supply a value of the column's expected type"),
        _spec("invalid_value", ERROR, VALIDATE,
              "the value is not a member of the column's closed vocabulary",
              "use a valid code (e.g. a country code like 'us', not 'Canada')"),
        _spec("invalid_join", ERROR, VALIDATE,
              'a branch join is not "and" or "or"',
              'use "and" or "or" to join conditions'),
        _spec("empty_branch", ERROR, VALIDATE,
              "a boolean branch has no conditions",
              "add at least one condition to the group, or remove it"),
        _spec("invalid_sample", ERROR, VALIDATE,
              "sample must be a positive integer",
              "give a positive count, e.g. sample 100"),
        _spec("invalid_group_by", ERROR, VALIDATE,
              "a group_by dimension is malformed or not groupable",
              "group by a groupable column"),
        _spec("invalid_select_column", ERROR, VALIDATE,
              "a selected field is not a valid result field",
              "select a field that exists on this entity"),
        _spec("invalid_pagination", ERROR, VALIDATE,
              "page and cursor are mutually exclusive",
              "use either page or cursor pagination, not both"),
        _spec("invalid_per_page", ERROR, VALIDATE,
              "per_page is outside the allowed range",
              "use a per_page between 1 and 200"),
        _spec("invalid_page", ERROR, VALIDATE,
              "page must be a positive integer",
              "use a page number of 1 or more"),
        _spec("invalid_sort_order", ERROR, VALIDATE,
              "the sort order is not allowed for this column",
              "use a permitted sort order (relevance_score sorts desc only)"),
        _spec("invalid_sort_aggregate", ERROR, VALIDATE,
              "the sort aggregate is not a recognized aggregate",
              "use a recognized aggregate (count / sum(...) / mean(...) …)"),
        _spec("invalid_sort_aggregate_column", ERROR, VALIDATE,
              "the aggregate's column is not valid for this group_by",
              "aggregate over a groupable/metric column"),
        _spec("relevance_sort_requires_search", ERROR, VALIDATE,
              "sorting by relevance_score requires a search clause",
              "add a search condition, or sort by another field"),
        _spec("aggregate_sort_requires_group_by", ERROR, VALIDATE,
              "sorting by an aggregate requires a group_by",
              "add a group_by, or sort by a plain column"),
        _spec("seed_without_sample", WARNING, VALIDATE,
              "a seed has no effect without a sample",
              "add a sample N, or drop the seed"),
    ]
}


# --- accessors ----------------------------------------------------------------
def is_registered(code: str) -> bool:
    return code in DIAGNOSTICS


def spec_for(code: str) -> Optional[DiagnosticSpec]:
    return DIAGNOSTICS.get(code)


def default_fixit(code: str) -> str:
    """The canonical fix-it for ``code`` (``""`` if the code is unregistered)."""
    s = DIAGNOSTICS.get(code)
    return s.default_fixit if s else ""


def severity_of(code: str, default: str = ERROR) -> str:
    s = DIAGNOSTICS.get(code)
    return s.severity if s else default


# --- unified editor diagnostic ------------------------------------------------
@dataclass
class Diagnostic:
    """One normalized diagnostic for the editor surface (#357), spanning both the
    parse layer (``OQL_*`` with a byte ``start``/``end``) and the validate layer
    (``invalid_*`` with an OQO JSON-path ``location``). Built through the helpers
    below so every surface emits the same shape AND every diagnostic — including
    validation ones, which historically had none — carries a registry fix-it.
    """

    code: str
    message: str
    fixit: str
    severity: str
    start: Optional[int] = None
    end: Optional[int] = None
    location: Optional[str] = None
    # The offending node's decimal address as a list of ints, GraphQL
    # `errors[].path` style (oxjob #474) — set for validation diagnostics on a
    # filter node, None for parse errors (no tree yet) and non-filter locations.
    path: Optional[List[int]] = None

    def to_dict(self) -> Dict[str, object]:
        return {
            "code": self.code, "message": self.message, "fixit": self.fixit,
            "severity": self.severity, "start": self.start, "end": self.end,
            "location": self.location, "path": self.path,
        }


def parse_diagnostic(e: OQLError) -> Diagnostic:
    """Normalize a parser ``OQLError`` (its byte position spans start==end)."""
    return Diagnostic(
        code=e.code, message=e.message,
        fixit=e.fixit or default_fixit(e.code),
        severity=severity_of(e.code),
        start=e.position, end=e.position, location=None,
    )


def validation_diagnostic(code: str, message: str,
                          location: Optional[str] = None,
                          path: Optional[List[int]] = None) -> Diagnostic:
    """Normalize an OQO ``ValidationError`` — supplying the fix-it and severity the
    validator's own (``type``, ``message``, ``location``) shape never carried.

    ``path`` (oxjob #474) is the offending node's decimal address (list of ints),
    resolved from ``location`` by the caller; None for non-filter locations."""
    return Diagnostic(
        code=code, message=message,
        fixit=default_fixit(code), severity=severity_of(code),
        start=None, end=None, location=location, path=path,
    )


def oql_error(code: str, message: Optional[str] = None, fixit: Optional[str] = None,
              position: Optional[int] = None) -> OQLError:
    """Construct an :class:`OQLError` through the registry.

    Validates that ``code`` is registered (a dev-time guard against typos and ghost
    codes — historically e.g. ``OQL_WILDCARD_IN_QUOTES`` lingered in comments). When
    ``message``/``fixit`` are omitted, falls back to the spec's ``summary`` /
    ``default_fixit`` so every diagnostic carries an actionable fix-it even at the
    raise sites that previously passed an empty string.
    """
    spec = DIAGNOSTICS.get(code)
    assert spec is not None, f"unregistered OQL diagnostic code: {code!r}"
    msg = message if message is not None else spec.summary
    fix = fixit if fixit else spec.default_fixit
    return OQLError(code, msg, fix, position)
