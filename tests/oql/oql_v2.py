"""
OQL v2 — reference implementation (the *executable spec*).

This module is the runnable embodiment of `docs/oql-spec.md` v2: a parser
(OQL text -> OQO) and a renderer (OQO -> OQL text) that implement the locked
design decisions from oxjob #330 (EXPLORE.md §2). It exists so the normative
corpus (`docs/oql/corpus.yaml`) can be machine-checked for round-trip identity
(`OQO -> OQL -> OQO` is the identity).

It is deliberately SEPARATE from the production translator in
`query_translation/oql_*.py`, which is still the v1.1 surface. Reconciling that
production code is roadmap step 3 (gated on #323); this job only emits the gap
report that feeds it. Think of this file as the conformance oracle, not the
shipping library.

Design anchors (see docs/oql-spec.md for the prose, EXPLORE.md for the why):
- Governing law: outside quotes = structure; inside quotes = literal text.
- Mixed AND/OR at one grouping level is a loud error (parens required).
- No implicit adjacency: two operands with no connective is an error.
- `[...]` is an ignored annotation; the ID is authoritative.
- `(...)` does double duty: boolean grouping AND value lists (`is any of (...)`).
- Only `"` delimits strings; there are no escape sequences.
- Quotes = phrase with stemming ON; `exactly` = non-stemmed; `within N words` =
  whole-phrase proximity; `is similar to` = semantic. Wildcards `* ?` fire only
  bare; in quotes / leading / sub-3-char-prefix / in-proximity are errors.
"""
from __future__ import annotations

import os
import re
import sys
from dataclasses import dataclass
from typing import List, Optional, Tuple, Union

# Load the OQO data model without triggering the Flask-heavy package __init__.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import tests.oql._qt_loader  # noqa: F401  (registers the stub package)
from query_translation.oqo import OQO, LeafFilter, BranchFilter, FilterType, GroupBy, SortBy  # noqa: E402


# ---------------------------------------------------------------------------
# Diagnostics — a named code + human message + fix-it for every error/hint.
# Codes are the language-agnostic contract (charter decision 5); prose localizes.
# ---------------------------------------------------------------------------
class OQLError(Exception):
    def __init__(self, code: str, message: str, fixit: str = "", position: Optional[int] = None):
        self.code = code
        self.message = message
        self.fixit = fixit
        self.position = position
        super().__init__(f"[{code}] {message}" + (f"  Fix: {fixit}" if fixit else ""))


# Hints are non-fatal: collected on the parse, never raised.
@dataclass
class OQLHint:
    code: str
    message: str
    fixit: str = ""


# ---------------------------------------------------------------------------
# Field / column registry (a focused stand-in for the #294/#331 properties
# registry). Maps human + technical OQL field names to OQO column ids + a kind.
# ---------------------------------------------------------------------------
# kind: 'search' (column = base; real id = base + .search[.exact|.semantic])
#       'bool'   (value is true/false; optional human "it's ..." phrasing)
#       'num'    (int comparison + equality)
#       'id'     (entity id equality / set)
#       'enum'   (slug equality / set)
#       'string' (literal-string equality, e.g. doi/orcid)
# The engine is fully case-insensitive on values (verified live 2026-06-02:
# US==us, Article==article, I136…==i136…), so value case is purely cosmetic.
# We canonicalize for readability, NOT correctness:
#   casing 'lower'  -> enum slugs (article, gold, en)
#   casing 'upper'  -> ISO country codes (US, GB) — convention, what people read
#   casing ''       -> IDs / strings / search text: preserved verbatim (an
#                      OpenAlex ID's uppercase prefix is its conventional form;
#                      search text is the user's literal text). col_… refs are
#                      ALWAYS preserved regardless of casing (they self-identify).
# resolves_name: the renderer synthesizes a `[display name]` for this column's
# values (opaque IDs + country codes), via an entity resolver. Human-readable
# slugs (article, gold, en) don't — `article [article]` is noise.
@dataclass
class Field:
    column: str          # base column (search) or full column_id (non-search)
    kind: str
    oql: str             # canonical OQL spelling for rendering
    bool_true: str = ""  # human phrasing for value=true   (bool kind)
    bool_false: str = "" # human phrasing for value=false  (bool kind)
    casing: str = ""     # '' | 'lower' | 'upper'
    resolves_name: bool = False


_FIELDS: List[Tuple[List[str], Field]] = []  # (alias-spellings, Field)


def _f(oql, column, kind, aliases=(), bool_true="", bool_false="",
       casing=None, resolves_name=None):
    if casing is None:
        casing = "lower" if kind == "enum" else ""
    if resolves_name is None:
        resolves_name = (kind == "id")
    fld = Field(column=column, kind=kind, oql=oql, bool_true=bool_true,
                bool_false=bool_false, casing=casing, resolves_name=resolves_name)
    spellings = [oql] + list(aliases)
    _FIELDS.append(([s.lower() for s in spellings], fld))
    return fld


def _canon_value_case(value, fld: "Field"):
    """Apply the column's cosmetic value casing (never touches col_… refs)."""
    if not isinstance(value, str) or value.startswith("col_") or not fld.casing:
        return value
    return value.lower() if fld.casing == "lower" else value.upper()


# --- search fields (column is the *base*; .search suffix added per mode) ---
_f("title", "display_name", "search", aliases=["display_name.search", "display_name"])
_f("title & abstract", "title_and_abstract", "search",
   aliases=["title and abstract", "title_and_abstract.search", "title_and_abstract", "title&abstract"])
_f("abstract", "abstract", "search", aliases=["abstract.search"])
_f("fulltext", "fulltext", "search", aliases=["fulltext.search", "full text"])
_f("anywhere", "default", "search", aliases=["default", "default.search", "any field"])
_f("raw affiliation", "raw_affiliation_strings", "search",
   aliases=["raw_affiliation_strings.search", "affiliation", "raw affiliation string"])
_f("byline", "raw_author_name", "search",
   aliases=["raw_author_name.search", "raw author name"])
_f("institution name", "institutions.display_name", "search",
   aliases=["institutions.display_name.search"])

# --- numeric ---
_f("year", "publication_year", "num", aliases=["publication_year"])
_f("citations", "cited_by_count", "num", aliases=["cited_by_count", "cited by count"])
_f("FWCI", "fwci", "num", aliases=["fwci"])

# --- booleans ---
_f("open access", "open_access.is_oa", "bool", aliases=["open_access.is_oa"],
   bool_true="it's open access", bool_false="it's not open access")
_f("from global south", "institutions.is_global_south", "bool",
   aliases=["institutions.is_global_south"],
   bool_true="it's from the global south", bool_false="it's not from the global south")
_f("retracted", "is_retracted", "bool", aliases=["is_retracted"],
   bool_true="it's retracted", bool_false="it's not retracted")
_f("has a DOI", "has_doi", "bool", aliases=["has_doi"],
   bool_true="it has a DOI", bool_false="it doesn't have a DOI")
_f("has an ORCID", "has_orcid", "bool", aliases=["has_orcid"],
   bool_true="it has an ORCID", bool_false="it doesn't have an ORCID")

# --- ids (entity references) ---
_f("institution", "authorships.institutions.lineage", "id",
   aliases=["authorships.institutions.lineage"])
_f("author", "authorships.author.id", "id", aliases=["authorships.author.id"])
_f("source", "primary_location.source.id", "id", aliases=["primary_location.source.id"])
_f("topic", "primary_topic.id", "id", aliases=["primary_topic.id"])
_f("topics", "topics.id", "id", aliases=["topics.id"])
_f("funder", "funders.id", "id", aliases=["funders.id", "grants.funder"])
_f("SDG", "sustainable_development_goals.id", "id",
   aliases=["sustainable_development_goals.id", "sustainable development goals", "sdg"])
_f("last known institution", "last_known_institutions.id", "id",
   aliases=["last_known_institutions.id"])
_f("domain", "domain.id", "id", aliases=["domain.id"])
_f("field", "primary_topic.field.id", "id", aliases=["primary_topic.field.id"])
_f("openalex id", "ids.openalex", "id", aliases=["ids.openalex"])

# --- enums (slug values) ---
_f("type", "type", "enum", aliases=[])
_f("OA status", "open_access.oa_status", "enum", aliases=["open_access.oa_status", "oa status"])
# Country codes: ISO uppercase canonical + resolve a [display name] (Germany, not de).
_f("country", "authorships.countries", "enum", aliases=["authorships.countries"],
   casing="upper", resolves_name=True)
_f("country code", "country_code", "enum", aliases=["country_code"],
   casing="upper", resolves_name=True)
_f("author country", "last_known_institutions.country_code", "enum",
   aliases=["last_known_institutions.country_code"], casing="upper", resolves_name=True)
_f("language", "language", "enum", aliases=[])

# --- literal strings ---
_f("DOI", "doi", "string", aliases=["doi"])
_f("ORCID", "authorships.author.orcid", "string", aliases=["authorships.author.orcid", "author orcid"])

# Reverse map: column_id (final, incl. search suffix stripped to base) -> Field
_BY_COLUMN = {}
for _spellings, _fld in _FIELDS:
    _BY_COLUMN.setdefault(_fld.column, _fld)

# alias-string -> Field, and the max alias word-length for greedy matching
_ALIAS = {}
for _spellings, _fld in _FIELDS:
    for s in _spellings:
        _ALIAS[s] = _fld

ENTITY_TYPES = {
    "works", "authors", "institutions", "sources", "publishers", "funders",
    "topics", "keywords", "concepts", "countries", "continents", "domains",
    "fields", "subfields", "sdgs", "languages", "licenses", "types",
    "source types", "institution types", "awards",
}

_CONNECTIVES = {"and", "or"}


# ---------------------------------------------------------------------------
# Lexer
# ---------------------------------------------------------------------------
@dataclass
class Tok:
    kind: str   # WORD | STRING | ANNOT | LP | RP | COMMA | OP | SEMI
    val: str
    pos: int


_WORD_BREAK = set(' \t\n"[](),;')


def lex(s: str) -> List[Tok]:
    toks: List[Tok] = []
    i, n = 0, len(s)
    while i < n:
        c = s[i]
        if c in ' \t\n':
            i += 1
            continue
        if c == '"':
            j = s.find('"', i + 1)
            if j == -1:
                raise OQLError("OQL_UNTERMINATED_STRING",
                               f'unterminated string starting at position {i}',
                               'add a closing double-quote (")', i)
            toks.append(Tok("STRING", s[i + 1:j], i))
            i = j + 1
            continue
        if c == '[':
            j = s.find(']', i + 1)
            if j == -1:
                raise OQLError("OQL_UNTERMINATED_ANNOTATION",
                               f'unterminated annotation [ starting at position {i}',
                               'add a closing bracket (])', i)
            toks.append(Tok("ANNOT", s[i + 1:j], i))
            i = j + 1
            continue
        if c == '(':
            toks.append(Tok("LP", c, i)); i += 1; continue
        if c == ')':
            toks.append(Tok("RP", c, i)); i += 1; continue
        if c == ',':
            toks.append(Tok("COMMA", c, i)); i += 1; continue
        if c == ';':
            toks.append(Tok("SEMI", c, i)); i += 1; continue
        if c in '><':
            op = c
            if i + 1 < n and s[i + 1] == '=':
                op += '='
            toks.append(Tok("OP", op, i)); i += len(op); continue
        # WORD: run until a break char
        j = i
        while j < n and s[j] not in _WORD_BREAK:
            j += 1
        toks.append(Tok("WORD", s[i:j], i))
        i = j
    return toks


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------
class _Parser:
    def __init__(self, toks: List[Tok]):
        self.toks = toks
        self.i = 0
        self.hints: List[OQLHint] = []

    # -- token helpers --
    def peek(self, k=0) -> Optional[Tok]:
        j = self.i + k
        return self.toks[j] if j < len(self.toks) else None

    def next(self) -> Tok:
        t = self.toks[self.i]
        self.i += 1
        return t

    def at_end(self) -> bool:
        # ANNOT tokens are inert trivia — skip them when checking for end.
        self._skip_annot()
        return self.i >= len(self.toks)

    def _skip_annot(self):
        while self.i < len(self.toks) and self.toks[self.i].kind == "ANNOT":
            self.i += 1

    def word_is(self, *words, k=0) -> bool:
        t = self.peek(k)
        return bool(t and t.kind == "WORD" and t.val.lower() in {w.lower() for w in words})

    # -- entry --
    def parse(self) -> OQO:
        self._skip_annot()
        entity = self._parse_entity()
        filters: List[FilterType] = []
        sort_by: List[SortBy] = []
        group_by: List[GroupBy] = []
        sample = None
        seed = None
        self._skip_annot()
        if self.word_is("where"):
            self.next()
            cond = self._parse_expr(top=True)
            # Top-level filter_rows is an implicit AND -> flatten the AND tree
            # transitively (the canonicalizer does not merge AND-branches that
            # sit as top-level filter_rows elements, so we produce the flat form).
            if isinstance(cond, BranchFilter) and cond.join == "and" and not cond.is_negated:
                filters = _flatten_and(cond)
            else:
                filters = [cond]
        # directives
        while True:
            self._skip_annot()
            t = self.peek()
            if t is None:
                break
            if t.kind == "SEMI":
                self.next()
                continue
            if t.kind == "WORD" and t.val.lower() == "sort" and self.word_is("by", k=1):
                self.i += 2
                sort_by = self._parse_sort()
            elif t.kind == "WORD" and t.val.lower() == "group" and self.word_is("by", k=1):
                self.i += 2
                group_by = self._parse_group_by()
            elif t.kind == "WORD" and t.val.lower() == "sample":
                self.next()
                sample, seed = self._parse_sample()
            else:
                raise OQLError("OQL_TRAILING_TOKENS",
                               f'unexpected text near "{t.val}" (position {t.pos})',
                               'queries are: <entity> [where <conditions>] [; sort by ...] '
                               '[; group by ...] [; sample N]', t.pos)
        return OQO(get_rows=entity, filter_rows=filters, sort_by=sort_by,
                   group_by=group_by, sample=sample, seed=seed)

    def _parse_entity(self) -> str:
        # Greedy longest match against ENTITY_TYPES (handles "source types").
        t = self.peek()
        if t is None or t.kind != "WORD":
            raise OQLError("OQL_MISSING_ENTITY",
                           "a query must start with an entity type",
                           'e.g. "works where ..."', t.pos if t else None)
        # try two-word then one-word
        two = None
        if self.peek(1) and self.peek(1).kind == "WORD":
            two = f"{t.val} {self.peek(1).val}".lower()
        if two in ENTITY_TYPES:
            self.i += 2
            return two.replace(" types", "-types").replace(" ", "-") if two not in ("source types", "institution types") else two.replace(" ", "-")
        one = t.val.lower()
        if one in ENTITY_TYPES:
            self.next()
            return one
        raise OQLError("OQL_UNKNOWN_ENTITY",
                       f'unknown entity type "{t.val}"',
                       f'use one of: works, authors, institutions, sources, ...', t.pos)

    # -- boolean expression with single-connective-per-level enforcement --
    def _parse_expr(self, top=False) -> FilterType:
        operands = [self._parse_operand()]
        conns: List[str] = []
        while True:
            self._skip_annot()
            t = self.peek()
            if t is None or t.kind in ("RP", "SEMI"):
                break
            if t.kind == "WORD" and t.val.lower() == "not":
                # NOT at a connective position means "a NOT b" with no AND/OR.
                self._adjacency_error(t)
            if t.kind == "WORD" and t.val.lower() in _CONNECTIVES:
                conns.append(t.val.lower())
                self.next()
                operands.append(self._parse_operand())
                continue
            # directive keywords end the where-expression
            if t.kind == "WORD" and t.val.lower() in ("sort", "group", "sample"):
                break
            # anything else with no connective = implicit adjacency
            self._adjacency_error(t)
        if not conns:
            return operands[0]
        if len(set(conns)) > 1:
            first = self.toks[0]
            raise OQLError(
                "OQL_MIXED_BOOL_NEEDS_PARENS",
                "mixed AND/OR at one level is ambiguous — add parentheses",
                'group explicitly, e.g. "a and (b or c)" or "(a and b) or c"',
                first.pos)
        join = conns[0]
        return BranchFilter(join=join, filters=operands)

    def _adjacency_error(self, t: Tok):
        raise OQLError("OQL_IMPLICIT_ADJACENCY",
                       f'two conditions with no AND/OR between them (near "{t.val}")',
                       'insert an explicit AND or OR', t.pos)

    def _parse_operand(self) -> FilterType:
        self._skip_annot()
        t = self.peek()
        if t is None:
            raise OQLError("OQL_EMPTY", "expected a condition", "")
        if t.kind == "WORD" and t.val.lower() == "not":
            self.next()
            inner = self._parse_operand()
            return _negate(inner)
        if t.kind == "LP":
            self.next()
            e = self._parse_expr()
            self._expect_rp()
            return e
        return self._parse_clause()

    def _expect_rp(self):
        self._skip_annot()
        t = self.peek()
        if t is None or t.kind != "RP":
            raise OQLError("OQL_UNBALANCED_PARENS", "missing a closing parenthesis",
                           "add a )", t.pos if t else None)
        self.next()

    # -- clauses --
    def _parse_clause(self) -> FilterType:
        self._skip_annot()
        # boolean human form: it's / its / it
        if self.word_is("it's", "its", "it"):
            return self._parse_boolean_clause()
        field, fld = self._parse_field()
        op = self._parse_operator()
        if fld.kind == "search":
            if op == "similar":
                return self._parse_semantic(fld)
            if op not in ("contains", "ncontains"):
                raise OQLError("OQL_BAD_OPERATOR_FOR_FIELD",
                               f'search field "{field}" needs "contains" (not "{op}")',
                               'use: <field> contains <terms>')
            tree = self._parse_search_expr(fld.column)
            if op == "ncontains":
                tree = _negate(tree)
            return tree
        # non-search
        if op in ("contains", "ncontains", "similar"):
            raise OQLError("OQL_BAD_OPERATOR_FOR_FIELD",
                           f'field "{field}" does not support "{op}"',
                           'use "is" / a comparison')
        return self._parse_value_clause(field, fld, op)

    def _parse_field(self) -> Tuple[str, Field]:
        # greedy longest alias match (up to 4 words)
        best = None
        best_len = 0
        parts = []
        for k in range(0, 4):
            t = self.peek(k)
            if not t or t.kind != "WORD":
                break
            parts.append(t.val)
            key = " ".join(parts).lower()
            if key in _ALIAS:
                best = _ALIAS[key]
                best_len = k + 1
        if best is None:
            t = self.peek()
            raise OQLError("OQL_UNKNOWN_FIELD",
                           f'unknown field "{t.val if t else ""}"',
                           'check the field name against the properties registry',
                           t.pos if t else None)
        spelling = " ".join(self.toks[self.i + k].val for k in range(best_len))
        self.i += best_len
        return spelling, best

    def _parse_operator(self) -> str:
        self._skip_annot()
        t = self.peek()
        if t is None:
            raise OQLError("OQL_MISSING_OPERATOR", "expected an operator", "")
        if t.kind == "OP":
            self.next()
            return t.val
        if t.kind == "WORD":
            w = t.val.lower()
            if w == "contains":
                self.next()
                return "contains"
            if w == "is":
                self.next()
                # is similar to | is not any of | is any of | is in | is not | is
                if self.word_is("similar") and self.word_is("to", k=1):
                    self.i += 2
                    return "similar"
                if self.word_is("not"):
                    self.next()
                    if self.word_is("any") and self.word_is("of", k=1):
                        self.i += 2
                        return "nin"
                    if self.word_is("in"):
                        self.next()
                        return "nin"
                    return "isnot"
                if self.word_is("any") and self.word_is("of", k=1):
                    self.i += 2
                    return "in"
                if self.word_is("in"):
                    self.next()
                    return "in"
                return "is"
            if w in ("does", "doesn't", "doesnt") :
                # does not contain / doesn't contain
                self.next()
                if self.word_is("not"):
                    self.next()
                if self.word_is("contain"):
                    self.next()
                    return "ncontains"
                raise OQLError("OQL_MISSING_OPERATOR", 'expected "does not contain"', "")
        raise OQLError("OQL_MISSING_OPERATOR",
                       f'expected an operator, got "{t.val}"',
                       'e.g. is / is any of / contains / >= ', t.pos)

    def _parse_boolean_clause(self) -> LeafFilter:
        # it's [not] <bool-field-phrase>  |  it has a <x> | it doesn't have a <x>
        self.next()  # consume it's/its/it
        negate = False
        if self.word_is("not"):
            self.next()
            negate = True
        if self.word_is("doesn't", "doesnt"):
            self.next()
            negate = True
        if self.word_is("has", "have"):
            self.next()
        # consume optional article words
        while self.word_is("a", "an", "the", "from"):
            self.next()
        # read the rest of the phrase words until a connective / end / paren
        parts = []
        while True:
            t = self.peek()
            if not t or t.kind != "WORD" or t.val.lower() in _CONNECTIVES \
               or t.val.lower() in ("sort", "group", "sample"):
                break
            parts.append(t.val)
            self.next()
        phrase = " ".join(parts).lower().strip()
        # map phrase -> bool field
        # try direct field alias, plus a couple of natural phrasings
        candidates = [phrase, "has " + phrase, phrase + "", "from " + phrase]
        fld = None
        for c in candidates:
            if c in _ALIAS and _ALIAS[c].kind == "bool":
                fld = _ALIAS[c]
                break
        # special phrasings
        if fld is None:
            alt = {
                "doi": "has a DOI", "orcid": "has an ORCID",
                "global south": "from global south",
            }.get(phrase)
            if alt:
                fld = _ALIAS[alt.lower()]
        if fld is None:
            raise OQLError("OQL_UNKNOWN_BOOLEAN",
                           f'unknown boolean property "{phrase}"',
                           'e.g. "it\'s open access", "it has a DOI"')
        return LeafFilter(column_id=fld.column, value=(False if negate else True), operator="is")

    def _parse_value_clause(self, field: str, fld: Field, op: str) -> FilterType:
        # (no _skip_annot here — _parse_scalar must SEE a lone annotation so it
        # can raise OQL_MISSING_ENTITY_ID for "institution is [Harvard]".)
        # set: is any of (...) / is not any of (...)
        if op in ("in", "nin"):
            vals = self._parse_value_list(fld)
            if op == "in":
                leaves = [LeafFilter(fld.column, v, "is") for v in vals]
                if len(leaves) == 1:
                    return leaves[0]
                return BranchFilter(join="or", filters=leaves)
            else:
                leaves = [LeafFilter(fld.column, v, "is", is_negated=True) for v in vals]
                if len(leaves) == 1:
                    return leaves[0]
                return BranchFilter(join="and", filters=leaves)
        # comparison
        if op in (">", ">=", "<", "<="):
            v = self._parse_scalar(fld)
            return LeafFilter(fld.column, v, op)
        # is / is not (incl. unknown/null)
        negated = (op == "isnot")
        if self.word_is("unknown", "null"):
            self.next()
            return LeafFilter(fld.column, None, "is", is_negated=negated)
        v = self._parse_scalar(fld)
        return LeafFilter(fld.column, v, "is", is_negated=negated)

    def _parse_value_list(self, fld: Field) -> list:
        self._skip_annot()
        t = self.peek()
        if not t or t.kind != "LP":
            raise OQLError("OQL_EXPECTED_LIST",
                           'expected a parenthesized list after "any of"',
                           'e.g. is any of (a, b, c)', t.pos if t else None)
        self.next()
        vals = []
        while True:
            vals.append(self._parse_scalar(fld))
            self._skip_annot()
            t = self.peek()
            if t and t.kind == "COMMA":
                self.next()
                continue
            break
        self._expect_rp()
        return vals

    def _parse_scalar(self, fld: Field):
        # An entity ref with only a [display name] annotation and no ID is the
        # classic v1.1 footgun — the ID is authoritative, so require it.
        if fld.kind == "id":
            t0 = self.peek()
            if t0 is not None and t0.kind == "ANNOT":
                raise OQLError("OQL_MISSING_ENTITY_ID",
                               f'"{fld.oql}" needs an ID, not just a [display name]',
                               'put the OpenAlex ID first, e.g. institution is I136199984 [Harvard]',
                               t0.pos)
        self._skip_annot()
        t = self.peek()
        if t is None:
            raise OQLError("OQL_MISSING_VALUE", f'expected a value for "{fld.oql}"', "")
        if t.kind == "STRING":
            self.next()
            val = t.val
        elif t.kind == "WORD":
            self.next()
            val = t.val
        else:
            raise OQLError("OQL_MISSING_VALUE",
                           f'expected a value for "{fld.oql}", got "{t.val}"', "", t.pos)
        self._skip_annot()  # drop a trailing [display name] annotation
        # type coercion per kind
        if fld.kind == "num":
            try:
                return int(val)
            except ValueError:
                raise OQLError("OQL_BAD_NUMBER",
                               f'"{val}" is not a number for "{fld.oql}"', "", t.pos)
        if fld.kind == "bool":
            low = val.lower()
            if low in ("true", "yes"):
                return True
            if low in ("false", "no"):
                return False
        return _canon_value_case(val, fld)

    # -- search sub-grammar --
    def _parse_semantic(self, fld: Field) -> LeafFilter:
        self._skip_annot()
        t = self.peek()
        if t is None or t.kind != "STRING":
            raise OQLError("OQL_SEMANTIC_NEEDS_TEXT",
                           '"is similar to" needs a quoted text passage',
                           'e.g. abstract is similar to "..."', t.pos if t else None)
        self.next()
        return LeafFilter(fld.column + ".search.semantic", t.val, "contains")

    def _parse_search_expr(self, base: str) -> FilterType:
        # A search expression is explicit-connective-separated *term-runs*. A
        # term-run is one or more space-adjacent atoms = implicit AND (the
        # everyday `climate change` = climate AND change). Implicit AND counts as
        # AND for the mixed-rule: mixing a space-run with an explicit `or` at one
        # level is a loud OQL_MIXED_BOOL_NEEDS_PARENS — we never silently pick an
        # order of operations. `climate change or warming` errors; the user must
        # say which they mean: `climate (change or warming)` or `(climate change) or warming`.
        unit, n = self._parse_term_run(base)
        units = [unit]
        implicit_and = n > 1
        conns: List[str] = []
        while True:
            self._skip_annot()
            t = self.peek()
            if t is None or t.kind in ("RP", "SEMI", "COMMA"):
                break
            if t.kind == "WORD" and t.val.lower() in _CONNECTIVES:
                if self._starts_new_clause(1):
                    break
                conns.append(t.val.lower())
                self.next()
                unit, n = self._parse_term_run(base)
                units.append(unit)
                implicit_and = implicit_and or n > 1
                continue
            break
        effective = set(conns) | ({"and"} if implicit_and else set())
        if "and" in effective and "or" in effective:
            raise OQLError(
                "OQL_MIXED_BOOL_NEEDS_PARENS",
                "mixed and/or at one level is ambiguous — add parentheses "
                "(a space between words is an AND)",
                'group explicitly, e.g. "a (b or c)" or "(a b) or c"', self.toks[0].pos)
        if not conns:
            return units[0]
        return BranchFilter(join=conns[0], filters=units)

    def _parse_term_run(self, base: str) -> Tuple[FilterType, int]:
        """One or more space-adjacent search atoms = implicit AND. Returns
        (filter, n_atoms) so the caller can apply the mixed-and/or rule."""
        atoms = [self._parse_search_operand(base)]
        while True:
            self._skip_annot()
            t = self.peek()
            if t is None or t.kind in ("RP", "SEMI", "COMMA"):
                break
            if t.kind == "WORD" and t.val.lower() in _CONNECTIVES:
                break  # explicit connective -> handled by _parse_search_expr
            if t.kind == "WORD" and t.val.lower() in ("sort", "group", "sample"):
                break
            if self._starts_new_clause(0):
                break  # a new field clause begins (e.g. `year >= 2020`)
            atoms.append(self._parse_search_operand(base))  # implicit AND
        if len(atoms) == 1:
            return atoms[0], 1
        return BranchFilter(join="and", filters=atoms), len(atoms)

    def _starts_new_clause(self, k: int) -> bool:
        """After a connective at offset k, do the tokens begin a new field clause?
        (a known field/boolean phrase followed by an operator)."""
        save = self.i
        self.i += k
        self._skip_annot()
        try:
            t = self.peek()
            if t and t.kind == "WORD" and t.val.lower() in ("it's", "its", "it"):
                return True
            # try to match a field alias
            parts = []
            matched = False
            for j in range(0, 4):
                tt = self.peek(j)
                if not tt or tt.kind != "WORD":
                    break
                parts.append(tt.val)
                if " ".join(parts).lower() in _ALIAS:
                    matched = True
                    after = self.peek(j + 1)
                    if after and (after.kind == "OP" or
                                  (after.kind == "WORD" and after.val.lower() in
                                   ("is", "contains", "does", "doesn't", "doesnt"))):
                        return True
            return False
        finally:
            self.i = save

    def _parse_search_operand(self, base: str) -> FilterType:
        self._skip_annot()
        t = self.peek()
        if t is None:
            raise OQLError("OQL_MISSING_VALUE", "expected a search term", "")
        if t.kind == "WORD" and t.val.lower() == "not":
            self.next()
            return _negate(self._parse_search_operand(base))
        if t.kind == "LP":
            self.next()
            e = self._parse_search_expr(base)
            self._expect_rp()
            return e
        # any of (...) / all of (...)
        if (t.kind == "WORD" and t.val.lower() in ("any", "all")
                and self.word_is("of", k=1)):
            join = "or" if t.val.lower() == "any" else "and"
            self.i += 2
            tt = self.peek()
            if not tt or tt.kind != "LP":
                raise OQLError("OQL_EXPECTED_LIST",
                               f'expected a list after "{t.val.lower()} of"',
                               'e.g. any of (a, b, c)', tt.pos if tt else None)
            self.next()
            leaves = []
            while True:
                leaves.append(self._parse_search_atom(base))
                self._skip_annot()
                nt = self.peek()
                if nt and nt.kind == "COMMA":
                    self.next()
                    continue
                break
            self._expect_rp()
            if len(leaves) == 1:
                return leaves[0]
            return BranchFilter(join=join, filters=leaves)
        return self._parse_search_atom(base)

    def _parse_search_atom(self, base: str) -> LeafFilter:
        # Stemming is ON by default; quotes turn it OFF (exact). `near "phrase"`
        # is the bridge: an adjacent phrase that STAYS stemmed (recall).
        #   bare term        -> stemmed          (.search)
        #   "phrase"         -> exact, adjacent  (.search.exact)
        #   near "phrase"    -> stemmed, adjacent (.search)
        self._skip_annot()
        stemmed_phrase = False
        if self.word_is("near") and self.peek(1) and self.peek(1).kind == "STRING":
            self.next()
            stemmed_phrase = True
        t = self.peek()
        if t is None or t.kind not in ("WORD", "STRING"):
            raise OQLError("OQL_MISSING_VALUE", "expected a search term",
                           "", t.pos if t else None)
        if t.kind == "STRING":
            text = t.val
            self.next()
            # A wildcard inside quotes is allowed ONLY as part of a proximity phrase
            # ("smart phone*" within N words) — the engine compiles it to an ES
            # `intervals` query (oxjob #355). Defer the decision: the proximity block
            # below validates and accepts it; a wildcard-in-quotes WITHOUT proximity is
            # rejected just after (OQL_WILDCARD_IN_QUOTES, e.g. "bar*").
            phrase = True
        else:
            text = t.val
            self.next()
            _validate_wildcards(text, t.pos)
            phrase = False
        # quoted => exact (.exact column) unless `near` keeps it stemmed
        stemmed = (not phrase) or stemmed_phrase
        col = base + (".search" if stemmed else ".search.exact")
        self._skip_annot()
        # proximity: within N words [of ...]
        if self.word_is("within"):
            self.next()
            nt = self.peek()
            if not nt or nt.kind != "WORD" or not nt.val.isdigit():
                raise OQLError("OQL_BAD_PROXIMITY", 'expected a number after "within"',
                               'e.g. within 3 words', nt.pos if nt else None)
            n = int(nt.val)
            self.next()
            if not self.word_is("words", "word"):
                raise OQLError("OQL_BAD_PROXIMITY", 'expected "words" after the number',
                               'e.g. within 3 words')
            self.next()
            if self.word_is("of"):
                raise OQLError("OQL_BINARY_PROXIMITY",
                               'binary "within N words of X" is not supported',
                               'use one quoted phrase: "term1 term2" within N words')
            has_wildcard = "*" in text or "?" in text
            # A bare (unquoted) wildcard token can't carry proximity
            # (e.g. `smart* within 3 words`).
            if has_wildcard and not phrase:
                raise OQLError("OQL_WILDCARD_IN_PROXIMITY",
                               'a wildcard cannot be combined with proximity',
                               'drop the wildcard, or drop "within N words"', t.pos)
            if not phrase or len(text.split()) < 2:
                raise OQLError("OQL_PROXIMITY_NEEDS_PHRASE",
                               'proximity needs a quoted multi-word phrase',
                               'e.g. "smart phone" within 3 words', t.pos)
            # A wildcard inside a quoted proximity phrase IS supported (oxjob #355): the
            # engine compiles it to an ES `intervals` query (trailing-prefix -> prefix
            # rule, mid-word `?` -> wildcard rule). Validate each wildcard token's shape
            # so #337's leading/short-prefix rejections still hold inside the phrase.
            if has_wildcard:
                for word in text.split():
                    _validate_wildcards(word, t.pos)
            return LeafFilter(col, f'"{text}"~{n}', "contains")
        # A wildcard inside quotes is only meaningful with proximity (handled above);
        # without a `within N words` suffix there is no engine path, so reject it
        # (e.g. `"bar*"`). (oxjob #337 / #355)
        if phrase and ("*" in text or "?" in text):
            raise OQLError("OQL_WILDCARD_IN_QUOTES",
                           f'wildcard inside a quoted phrase: "{text}"',
                           'move the wildcard out of the quotes, e.g. bar*', t.pos)
        # encode value: multi-word phrase keeps its quotes; a single word is bare
        # (the column suffix carries exact-vs-stemmed).
        if phrase and len(text.split()) > 1:
            value = f'"{text}"'
        else:
            value = text
        return LeafFilter(col, value, "contains")

    # -- directives --
    def _parse_sort(self) -> List[SortBy]:
        keys = []
        while True:
            field, col = self._parse_sort_field()
            direction = "asc"
            if self.word_is("desc", "descending"):
                self.next(); direction = "desc"
            elif self.word_is("asc", "ascending"):
                self.next(); direction = "asc"
            keys.append(SortBy(column_id=col, direction=direction))
            self._skip_annot()
            t = self.peek()
            if t and t.kind == "COMMA":
                self.next(); continue
            break
        return keys

    def _parse_sort_field(self) -> Tuple[str, str]:
        # accept a known field OR a bare technical column / synthetic key
        t = self.peek()
        if not t or t.kind != "WORD":
            raise OQLError("OQL_BAD_SORT", "expected a field to sort by", "")
        # try field alias
        for k in range(3, 0, -1):
            parts = [self.peek(j).val for j in range(k) if self.peek(j) and self.peek(j).kind == "WORD"]
            if len(parts) == k:
                key = " ".join(parts).lower()
                if key in _ALIAS:
                    self.i += k
                    return key, _ALIAS[key].column
        self.next()
        return t.val, t.val  # synthetic / technical (relevance_score, count, ...)

    def _parse_group_by(self) -> List[GroupBy]:
        dims = []
        while True:
            field, fld = self._parse_field()
            dims.append(GroupBy(column_id=fld.column))
            self._skip_annot()
            t = self.peek()
            if t and t.kind == "COMMA":
                self.next(); continue
            break
        return dims

    def _parse_sample(self):
        t = self.peek()
        if not t or t.kind != "WORD" or not t.val.isdigit():
            raise OQLError("OQL_BAD_SAMPLE", 'expected a number after "sample"',
                           'e.g. sample 100', t.pos if t else None)
        n = int(t.val)
        self.next()
        seed = None
        if self.word_is("seed"):
            self.next()
            st = self.peek()
            if st and st.kind in ("WORD", "STRING"):
                seed = st.val
                self.next()
        return n, seed


def _flatten_and(branch: BranchFilter) -> List[FilterType]:
    """Flatten an AND tree into a flat operand list (descend AND-branches; stop
    at OR-branches, negated branches, and leaves)."""
    out: List[FilterType] = []
    for f in branch.filters:
        if isinstance(f, BranchFilter) and f.join == "and" and not f.is_negated:
            out.extend(_flatten_and(f))
        else:
            out.append(f)
    return out


def _negate(f: FilterType) -> FilterType:
    if isinstance(f, LeafFilter):
        return LeafFilter(f.column_id, f.value, f.operator, is_negated=not f.is_negated)
    return BranchFilter(f.join, f.filters, is_negated=not f.is_negated)


def _validate_wildcards(word: str, pos: int):
    if "*" not in word and "?" not in word:
        return
    if word[0] in "*?":
        raise OQLError("OQL_LEADING_WILDCARD",
                       f'leading wildcard "{word}" is not supported (too expensive)',
                       'anchor the wildcard with leading characters, e.g. cycle*', pos)
    star = word.find("*")
    if star != -1:
        prefix = re.match(r"\w*", word).group(0)
        if star < 3 or len(prefix) < 3 or star > len(prefix):
            # require >=3 word chars immediately before the *
            chars_before = len(re.match(r"\w*", word).group(0)[:star])
            if chars_before < 3:
                raise OQLError("OQL_SHORT_WILDCARD_PREFIX",
                               f'wildcard needs at least 3 leading characters: "{word}"',
                               'add characters before the *, e.g. abc*', pos)
    q = word.find("?")
    if q != -1:
        if q == 0 or not (word[q - 1].isalnum()):
            raise OQLError("OQL_LEADING_WILDCARD",
                           f'"?" needs a character before it: "{word}"',
                           'e.g. wom?n', pos)


def parse(oql: str) -> OQO:
    """OQL text -> OQO. Raises OQLError (with .code/.fixit) on any error case."""
    toks = lex(oql)
    if not toks:
        raise OQLError("OQL_EMPTY", "empty query", 'e.g. "works where year >= 2020"')
    p = _Parser(toks)
    oqo = p.parse()
    return oqo


def parse_with_hints(oql: str):
    toks = lex(oql)
    p = _Parser(toks)
    return p.parse(), p.hints


# ---------------------------------------------------------------------------
# Renderer  (OQO -> canonical OQL text)
# ---------------------------------------------------------------------------
def _oql_field(column: str) -> Tuple[str, str]:
    """Return (oql_field_name, mode) for a column_id. mode in '', 'exact', 'semantic'."""
    mode = ""
    base = column
    if column.endswith(".search.semantic"):
        mode = "semantic"; base = column[: -len(".search.semantic")]
    elif column.endswith(".search.exact"):
        mode = "exact"; base = column[: -len(".search.exact")]
    elif column.endswith(".search"):
        base = column[: -len(".search")]
    fld = _BY_COLUMN.get(base) or _BY_COLUMN.get(column)
    name = fld.oql if fld else base
    return name, mode


def _is_search_leaf(f) -> bool:
    return isinstance(f, LeafFilter) and isinstance(f.column_id, str) and ".search" in f.column_id


def _render_term(value: str, column: str) -> str:
    """OQL surface form of one search value, given its column:
      .search (stemmed):       bare word | near "phrase" | near "phrase" within N words
      .search.exact (exact):   "word"    | "phrase"      | "phrase" within N words
    """
    stemmed = not column.endswith(".search.exact")  # .search (and anything else) stems
    prox = re.match(r'^"(.+)"~(\d+)$', value or "")
    if prox:
        body = f'"{prox.group(1)}" within {prox.group(2)} words'
        return f"near {body}" if stemmed else body
    if value.startswith('"') and value.endswith('"') and len(value) >= 2:  # multi-word phrase
        return f"near {value}" if stemmed else value
    # single word: stemmed => bare; exact => quoted
    return value if stemmed else f'"{value}"'


def _render_search_leaf(f: LeafFilter) -> str:
    name, mode = _oql_field(f.column_id)
    if mode == "semantic":
        v = (f.value or "").strip('"')
        return f'{name} is similar to "{v}"'
    verb = "does not contain" if f.is_negated else "contains"
    return f"{name} {verb} {_render_term(f.value, f.column_id)}"


def _render_value(fld, value) -> str:
    if value is None:
        return "unknown"
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _value_with_name(fld, value, resolver) -> str:
    """Render a value, appending ` [display name]` when the column resolves names
    and a resolver is supplied (institutions, authors, …, country codes)."""
    rendered = _render_value(fld, value)
    if (resolver and fld and fld.resolves_name and isinstance(value, str)
            and not value.startswith("col_")):
        name = resolver(value)
        if name:
            return f"{rendered} [{name}]"
    return rendered


def _render_leaf(f: LeafFilter, resolver=None) -> str:
    if _is_search_leaf(f):
        return _render_search_leaf(f)
    fld = _BY_COLUMN.get(f.column_id)
    name = fld.oql if fld else f.column_id
    # boolean human phrasing (a negated bool flips the value)
    if fld and fld.kind == "bool" and isinstance(f.value, bool):
        effective = f.value != f.is_negated  # XOR
        phrase = fld.bool_true if effective else fld.bool_false
        if phrase:
            return phrase
    if f.value is None:
        return f"{name} is {'not ' if f.is_negated else ''}unknown"
    if f.operator in (">", ">=", "<", "<="):
        return f"{name} {f.operator} {_render_value(fld, f.value)}"
    verb = "is not" if f.is_negated else "is"
    return f"{name} {verb} {_value_with_name(fld, f.value, resolver)}"


def _same_field_search_set(f: BranchFilter):
    """If every child is a plain search leaf on the same column & polarity, return
    (column, [values]); else None. Enables `field contains any of (...)`."""
    cols = set()
    vals = []
    for c in f.filters:
        if not (isinstance(c, LeafFilter) and _is_search_leaf(c) and not c.is_negated):
            return None
        _, mode = _oql_field(c.column_id)
        if mode == "semantic":  # semantic leaves don't fold into `contains any of`
            return None
        cols.add(c.column_id)
        vals.append(c.value)
    if len(cols) != 1:  # same column => same stemmed/exact mode => factorable
        return None
    return cols.pop(), vals


def _same_field_eq_set(f: BranchFilter, negated: bool):
    cols = set()
    vals = []
    want_join = "and" if negated else "or"
    if f.join != want_join:
        return None
    for c in f.filters:
        if not (isinstance(c, LeafFilter) and c.operator == "is"
                and c.is_negated == negated and not _is_search_leaf(c)
                and c.value is not None):
            return None
        cols.add(c.column_id)
        vals.append(c.value)
    if len(cols) != 1:
        return None
    return cols.pop(), vals


def _render_filter(f: FilterType, top=False, resolver=None) -> str:
    if isinstance(f, LeafFilter):
        return _render_leaf(f, resolver)
    # BranchFilter
    if f.is_negated:
        return "not (" + _render_filter(BranchFilter(f.join, f.filters), resolver=resolver) + ")"
    # factor same-field search OR/AND into `any of/all of`
    sset = _same_field_search_set(f)
    if sset:
        col, vals = sset
        name, _ = _oql_field(col)
        kw = "any of" if f.join == "or" else "all of"
        return f"{name} contains {kw} ({', '.join(_render_term(v, col) for v in vals)})"
    # factor same-field equality sets
    for neg in (False, True):
        eqset = _same_field_eq_set(f, neg)
        if eqset:
            col, vals = eqset
            fld = _BY_COLUMN.get(col)
            name = fld.oql if fld else col
            kw = "is not any of" if neg else "is any of"
            items = ", ".join(_value_with_name(fld, v, resolver) for v in vals)
            return f"{name} {kw} ({items})"
    parts = [_render_filter(c, resolver=resolver) for c in f.filters]
    joined = f" {f.join} ".join(parts)
    return joined if top else f"({joined})"


def render(oqo: OQO, resolver=None) -> str:
    """OQO -> canonical OQL. `resolver(id) -> name|None` (optional) synthesizes
    `[display name]` annotations for opaque-ID / country columns."""
    entity = oqo.get_rows.lower()
    out = entity
    if oqo.filter_rows:
        if len(oqo.filter_rows) == 1:
            cond = _render_filter(oqo.filter_rows[0], top=True, resolver=resolver)
        else:
            cond = " and ".join(_render_filter(f, resolver=resolver) for f in oqo.filter_rows)
        out += f" where {cond}"
    if oqo.group_by:
        dims = ", ".join(_oql_field(g.column_id)[0] for g in oqo.group_by)
        out += f"; group by {dims}"
    if oqo.sort_by:
        keys = []
        for s in oqo.sort_by:
            fld = _BY_COLUMN.get(s.column_id)
            name = fld.oql if fld else s.column_id
            keys.append(f"{name} {s.direction}")
        out += "; sort by " + ", ".join(keys)
    if oqo.sample:
        out += f"; sample {oqo.sample}"
        if oqo.seed is not None:
            out += f" seed {oqo.seed}"
    return out
