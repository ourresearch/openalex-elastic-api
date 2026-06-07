"""
OQL language engine (lexer + parser + field registry + canonical renderer).

This is the ONE production OQL engine. It was promoted verbatim from the v2
conformance oracle (`tests/oql/oql_v2.py`, oxjob #330); that file now re-exports
from here, so the "executable spec" and the shipping library are the same code
(oxjob #376, reconciling prod onto the oracle — formerly roadmap step 3 / #363).

Design anchors (see docs/oql-spec.md for prose, oxjob #330 EXPLORE.md for the why):
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

import re
from dataclasses import dataclass
from typing import List, Optional, Tuple, Union

# Load the OQO data model without triggering the Flask-heavy package __init__.
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
# "fulltext" is the canonical broad full-text scope: title + abstract + full text
# (oxjob #374). All broad-search spellings — including the old "anywhere" word and the
# deprecated "default.search" param name — fold in here and emit fulltext.search, so OQL
# never produces the deprecated default.search key. (Stray default.search columns from
# external URL→OQO still render to "fulltext" via the _BY_COLUMN alias below.)
_f("fulltext", "fulltext", "search",
   aliases=["fulltext.search", "full text", "anywhere", "any field", "default", "default.search"])
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

# --- collection (same-type membership) ---
# The same-type `collection:` filter: "this row's entity is a member of Collection
# col_…". Surfaced as `<subject> is in collection col_…` where the subject is the
# queried entity (works-centric registry → "work"). Cross-type membership reuses the
# referenced entity's own column (e.g. `country`/`institution`/`author`) — no separate
# field. kind "collection" parses a bare col_… scalar (no name resolution). (oxjob #363)
_f("work", "collection", "collection", aliases=["works"], resolves_name=False)

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
# default.search is the deprecated alias of fulltext.search (oxjob #374): render any
# stray default.search column (e.g. from an external URL→OQO) to the canonical
# "fulltext" word so it round-trips into fulltext.search.
_BY_COLUMN.setdefault("default", _BY_COLUMN["fulltext"])


def canon_value_for_column(value, column_id):
    """Apply a column's canonical value-casing by `column_id` (e.g. country codes
    -> upper, enum slugs -> lower). Public bridge so the OQO canonicalizer matches
    the parser's casing on the OQO-JSON submit path (oxjob: oqo-canonicalizer-enum-
    casing); the parser already routes every parsed value through `_canon_value_case`.
    Unknown columns and `col_…` set refs pass through untouched."""
    fld = _BY_COLUMN.get(column_id)
    return _canon_value_case(value, fld) if fld else value


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
                               'queries are: <entity> [where <conditions>] [sort by ...] '
                               '[group by ...] [sample N]', t.pos)
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
                    # `is not in collection` — MUST precede the bare `is not in`
                    # (= "is not any of") so "collection" isn't read as a value.
                    if self.word_is("in") and self.word_is("collection", k=1):
                        self.i += 2
                        return "nincoll"
                    if self.word_is("in"):
                        self.next()
                        return "nin"
                    return "isnot"
                if self.word_is("any") and self.word_is("of", k=1):
                    self.i += 2
                    return "in"
                # `is in collection` — MUST precede the bare `is in` (= "is any of").
                if self.word_is("in") and self.word_is("collection", k=1):
                    self.i += 2
                    return "incoll"
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
        # collection membership: is [not] in collection col_… (oxjob #363)
        if op in ("incoll", "nincoll"):
            v = self._parse_scalar(fld)
            if not (isinstance(v, str) and v.startswith("col_")):
                raise OQLError("OQL_BAD_COLLECTION_REF",
                               f'"is in collection" needs a collection id (col_…), got "{v}"',
                               'e.g. work is in collection col_abc123')
            return LeafFilter(fld.column, v, "in collection",
                              is_negated=(op == "nincoll"))
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
                # tolerate a trailing comma (the canonical formatter emits one
                # in every exploded list; #376 Phase 2): `(a, b,)` == `(a, b)`.
                nt = self.peek()
                if nt and nt.kind == "RP":
                    break
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
                    # tolerate a trailing comma (canonical formatter, #376 Ph2)
                    nt2 = self.peek()
                    if nt2 and nt2.kind == "RP":
                        break
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
        has_wildcard = "*" in text or "?" in text
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
                # Binary proximity `"A" within N words of "B"` — two SEPARATE quoted
                # operands NEAR each other (WoS `NEAR/N`). The engine compiles it to an
                # ES `intervals` query with one sub-interval per operand (oxjob #355
                # Goal B); `match_phrase`+slop can't express it (slop is whole-phrase).
                self.next()
                bt = self.peek()
                if bt is None or bt.kind != "STRING":
                    raise OQLError("OQL_BINARY_PROXIMITY_NEEDS_PHRASES",
                                   'binary proximity needs a quoted phrase after "of"',
                                   'e.g. "smart" within 3 words of "phone"',
                                   bt.pos if bt else None)
                right = bt.val
                self.next()
                # Binary proximity is exact-only (both operands quoted, no-stem). `near`
                # (stemmed) on operand A is not supported here.
                if not phrase or stemmed_phrase:
                    raise OQLError("OQL_BINARY_PROXIMITY_NEEDS_PHRASES",
                                   'binary proximity needs two quoted phrases',
                                   'e.g. "smart" within 3 words of "phone"', t.pos)
                # Validate each wildcard token's shape across BOTH operands (keep #337's
                # leading/short-prefix rejections), then the shared expansion budget
                # (#355 guard) across all tokens in the one intervals query.
                words = text.split() + right.split()
                for word in words:
                    _validate_wildcards(word, t.pos)
                _validate_wildcard_budget(words, t.pos)
                return LeafFilter(base + ".search.exact",
                                  f'"{text}"~{n}~"{right}"', "contains")
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
                _validate_wildcard_budget(text.split(), t.pos)
            return LeafFilter(col, f'"{text}"~{n}', "contains")
        # #364: outside a proximity phrase, a wildcard must run on exact (no-stem)
        # text — stemming at index time removes the literal prefix, so a wildcard
        # on a stemmed field is silently wrong (`studies*` = 2.4k stemmed vs 2.2M
        # no-stem). A bare term and a `near` phrase are stemmed → reject with a
        # quote-it fix-it. A quoted phrase is exact → the sanctioned wildcard path.
        # (This deliberately REVERSES #337's old OQL_WILDCARD_IN_QUOTES guidance:
        # quotes are now where wildcards belong.)
        if has_wildcard and stemmed:
            if stemmed_phrase:
                raise OQLError("OQL_WILDCARD_NEEDS_EXACT",
                               f'wildcards run on exact (no-stem) text, but "near" '
                               f'keeps the phrase stemmed: "{text}"',
                               'drop "near" so the wildcard runs on exact text', t.pos)
            raise OQLError("OQL_WILDCARD_NEEDS_EXACT",
                           f'wildcards run on exact (no-stem) text: {text}',
                           f'quote it: "{text}"', t.pos)
        # A quoted wildcard (`"studies*"`) is exact — validate each token's shape
        # so #337's leading / sub-3-char-prefix rejections still hold inside quotes.
        if phrase and has_wildcard:
            for word in text.split():
                _validate_wildcards(word, t.pos)
            _validate_wildcard_budget(text.split(), t.pos)
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


# oxjob #355 perf guard: cap prefix-expansion cost inside one ES `intervals` query
# (adjacency, single-phrase proximity, or binary proximity). Two short prefix-wildcards
# multiply postings expansion (live: `"pro* pro*"` ~265ms vs ~45ms once each prefix is
# >=4 chars). Mirrors core/search.py::_validate_wildcard_budget so OQL and the raw API
# reject identically. A lone wildcard is untouched (keeps #337's >=3-char floor).
MAX_WILDCARDS_PER_INTERVALS = 2
MULTI_WILDCARD_MIN_PREFIX = 4


def _validate_wildcard_budget(words: List[str], pos: int):
    wild = [w for w in words if "*" in w or "?" in w]
    if len(wild) <= 1:
        return
    if len(wild) > MAX_WILDCARDS_PER_INTERVALS:
        raise OQLError("OQL_TOO_MANY_WILDCARDS",
                       f'at most {MAX_WILDCARDS_PER_INTERVALS} wildcards are allowed in '
                       f'one phrase or proximity search (this has {len(wild)})',
                       'remove a wildcard, or split into separate searches', pos)
    for w in wild:
        # Only a trailing-`*` prefix drives multiplicative expansion; require a longer
        # anchor for it when a second wildcard is present.
        if w.endswith("*") and w.count("*") == 1 and "?" not in w:
            if len(w) - 1 < MULTI_WILDCARD_MIN_PREFIX:
                raise OQLError("OQL_MULTI_WILDCARD_SHORT_PREFIX",
                               f'with two wildcards in one phrase or proximity search, '
                               f'each * needs at least {MULTI_WILDCARD_MIN_PREFIX} '
                               f'leading characters (for performance): "{w}"',
                               'use a longer prefix (e.g. abcd*) or drop a wildcard', pos)


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
    # Binary proximity `"A"~N~"B"` -> `"A" within N words of "B"` (oxjob #355 Goal B).
    # Check before the single-phrase form below (whose regex won't match a value that
    # ends in a quote, but keep binary first for clarity). Binary is exact-only.
    binp = re.match(r'^"([^"]*)"~(\d+)~"([^"]*)"$', value or "")
    if binp:
        return (f'"{binp.group(1)}" within {binp.group(2)} words '
                f'of "{binp.group(3)}"')
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


def _call_resolver(resolver, value, column_id):
    """Resolve a value's display name. The engine resolver contract is
    `resolver(value, column_id)`; a legacy 1-arg `resolver(value)` is supported
    via fallback so the corpus harness's `lambda v: ...` keeps working."""
    if not resolver:
        return None
    try:
        return resolver(value, column_id)
    except TypeError:
        return resolver(value)


def _value_with_name(fld, value, column_id, resolver) -> str:
    """Render a value, appending ` [display name]` when the column resolves names
    and a resolver is supplied (institutions, authors, …, country codes)."""
    rendered = _render_value(fld, value)
    if (resolver and fld and fld.resolves_name and isinstance(value, str)
            and not value.startswith("col_")):
        name = _call_resolver(resolver, value, column_id)
        if name:
            return f"{rendered} [{name}]"
    return rendered


def _same_field_search_set(f: BranchFilter):
    """If every child is a plain search leaf on the same *base* field & polarity,
    return (name_column, [(value, column_id), ...]); else None. Enables
    `field contains any of (...)`. Grouping by base field (not full column_id)
    lets a mixed stemmed/exact list — `contains any of (obese, "body image")`,
    `.search` + `.search.exact` — factor into one clause; each value keeps its
    own column so `_render_term` renders its mode surface (bare vs quoted).
    Semantically identical to the OR/AND of the leaves, so round-trip holds."""
    bases = set()
    items = []
    name_col = None
    for c in f.filters:
        if not (isinstance(c, LeafFilter) and _is_search_leaf(c) and not c.is_negated):
            return None
        name, mode = _oql_field(c.column_id)
        if mode == "semantic":  # semantic leaves don't fold into `contains any of`
            return None
        bases.add(name)  # the human field name is the per-base identity
        if name_col is None:
            name_col = c.column_id
        items.append((c.value, c.column_id))
    if len(bases) != 1:  # one base field => factorable into a single clause
        return None
    return name_col, items


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


# ---------------------------------------------------------------------------
# Tree-emitting renderer.  The OQL string and the `oql_render` tree share ONE
# source of truth here: `render()` is literally `stringify(_build_tree(...))`,
# so Invariant A (`stringify(tree) == oql`) holds by construction. Every clause
# is a single ClauseNode whose segments concatenate to the canonical clause
# string; boolean structure is GroupNodes. The formatter (#376 Phase 2) hooks
# this one walk. The GUI consumes only the resulting `oql` string today, so the
# tree shape is free as long as the concatenation invariant holds.
# ---------------------------------------------------------------------------
from query_translation.oql_render_tree import (  # noqa: E402
    OQLRenderTree, EntityHead, GroupNode, ClauseNode, Segment, SegmentMeta,
    ClauseMeta, GroupMeta, EntityValue, SortDirective, SampleDirective,
    GroupByDirective, GroupByMeta, SortMeta, SampleMeta, ExprNode, stringify,
)


def _seg(kind, text, **meta):
    return Segment(kind=kind, text=text, meta=SegmentMeta(**meta) if meta else None)


def _value_segments(fld, value, column_id, resolver):
    """Segments for one value, mirroring `_value_with_name`: the bare value, then
    ` [name]` when the column resolves a display name. Concatenates to exactly
    what `_value_with_name` returns."""
    rendered = _render_value(fld, value)
    segs = [_seg("value", rendered, value=value, column_id=column_id)]
    entity = None
    if (resolver and fld and fld.resolves_name and isinstance(value, str)
            and not value.startswith("col_")):
        name = _call_resolver(resolver, value, column_id)
        if name:
            segs.append(_seg("text", " "))
            segs.append(_seg("id", f"[{name}]", entity_display_name=name,
                             entity_display_id=f"[{name}]"))
            entity = EntityValue(id=value, short_id=value, display_name=name)
    return segs, entity


def _leaf_node(f: LeafFilter, resolver=None) -> ClauseNode:
    if _is_search_leaf(f):
        name, mode = _oql_field(f.column_id)
        if mode == "semantic":
            v = (f.value or "").strip('"')
            segs = [_seg("column", name, column_id=f.column_id),
                    _seg("operator", " is similar to "),
                    _seg("value", f'"{v}"', value=f.value)]
        else:
            verb = "does not contain" if f.is_negated else "contains"
            segs = [_seg("column", name, column_id=f.column_id),
                    _seg("operator", f" {verb} "),
                    _seg("value", _render_term(f.value, f.column_id), value=f.value)]
        return ClauseNode(segments=segs, clause_kind="text", meta=ClauseMeta(
            column_id=f.column_id, operator=f.operator or "contains",
            value=f.value, column_display_name=name))

    fld = _BY_COLUMN.get(f.column_id)
    name = fld.oql if fld else f.column_id
    # boolean human phrasing (a negated bool flips the value)
    if fld and fld.kind == "bool" and isinstance(f.value, bool):
        effective = f.value != f.is_negated  # XOR
        phrase = fld.bool_true if effective else fld.bool_false
        if phrase:
            return ClauseNode(segments=[_seg("keyword", phrase)],
                              clause_kind="boolean", meta=ClauseMeta(
                                  column_id=f.column_id, operator="is",
                                  value=f.value, column_display_name=name))
    if f.value is None:
        op_text = f" is {'not ' if f.is_negated else ''}"
        segs = [_seg("column", name, column_id=f.column_id),
                _seg("operator", op_text), _seg("value", "unknown", value=None)]
        return ClauseNode(segments=segs, clause_kind="null", meta=ClauseMeta(
            column_id=f.column_id, operator="is", value=None,
            column_display_name=name))
    if f.operator in (">", ">=", "<", "<="):
        segs = [_seg("column", name, column_id=f.column_id),
                _seg("operator", f" {f.operator} "),
                _seg("value", _render_value(fld, f.value), value=f.value)]
        return ClauseNode(segments=segs, clause_kind="comparison", meta=ClauseMeta(
            column_id=f.column_id, operator=f.operator, value=f.value,
            column_display_name=name))
    if f.operator == "in collection":  # oxjob #363; col_… value, never name-resolved
        verb = "is not in collection" if f.is_negated else "is in collection"
        segs = [_seg("column", name, column_id=f.column_id),
                _seg("operator", f" {verb} "),
                _seg("value", _render_value(fld, f.value), value=f.value)]
        return ClauseNode(segments=segs, clause_kind="collection", meta=ClauseMeta(
            column_id=f.column_id, operator="in collection", value=f.value,
            column_display_name=name))
    verb = "is not" if f.is_negated else "is"
    val_segs, entity = _value_segments(fld, f.value, f.column_id, resolver)
    segs = [_seg("column", name, column_id=f.column_id),
            _seg("operator", f" {verb} ")] + val_segs
    kind = "entity" if (fld and fld.kind == "id") else "other"
    return ClauseNode(segments=segs, clause_kind=kind, meta=ClauseMeta(
        column_id=f.column_id, operator="is", value=f.value,
        column_display_name=name, value_entity=entity))


def _filter_node(f: FilterType, top=False, resolver=None) -> ExprNode:
    if isinstance(f, LeafFilter):
        return _leaf_node(f, resolver)
    # BranchFilter
    if f.is_negated:
        inner = _filter_node(BranchFilter(f.join, f.filters), top=False, resolver=resolver)
        return GroupNode(join=f.join, children=[inner], prefix="not (", suffix=")",
                         joiner="", meta=GroupMeta(implicit=False))
    # factor same-field search OR/AND into `any of/all of` -> one value-list clause
    sset = _same_field_search_set(f)
    if sset:
        col, items = sset
        name, _ = _oql_field(col)
        kw = "any of" if f.join == "or" else "all of"
        segs = [_seg("column", name, column_id=col),
                _seg("operator", f" contains {kw} "), _seg("text", "(")]
        for i, (v, vcol) in enumerate(items):
            if i:
                segs.append(_seg("text", ", "))
            segs.append(_seg("value", _render_term(v, vcol), value=v))
        segs.append(_seg("text", ")"))
        return ClauseNode(segments=segs, clause_kind="text", meta=ClauseMeta(
            column_id=col, operator="contains", value=None,
            column_display_name=name))
    # factor same-field equality sets -> one value-list clause
    for neg in (False, True):
        eqset = _same_field_eq_set(f, neg)
        if eqset:
            col, vals = eqset
            fld = _BY_COLUMN.get(col)
            name = fld.oql if fld else col
            kw = "is not any of" if neg else "is any of"
            segs = [_seg("column", name, column_id=col),
                    _seg("operator", f" {kw} "), _seg("text", "(")]
            for i, v in enumerate(vals):
                if i:
                    segs.append(_seg("text", ", "))
                segs.extend(_value_segments(fld, v, col, resolver)[0])
            segs.append(_seg("text", ")"))
            kind = "entity" if (fld and fld.kind == "id") else "other"
            return ClauseNode(segments=segs, clause_kind=kind, meta=ClauseMeta(
                column_id=col, operator="is", value=None,
                column_display_name=name))
    children = [_filter_node(c, top=False, resolver=resolver) for c in f.filters]
    joiner = f" {f.join} "
    prefix, suffix = ("", "") if top else ("(", ")")
    return GroupNode(join=f.join, children=children, prefix=prefix, suffix=suffix,
                     joiner=joiner, meta=GroupMeta(implicit=False))


def _build_tree(oqo: OQO, resolver=None) -> OQLRenderTree:
    """OQO -> canonical `oql_render` tree. `render()` stringifies this; the two
    never drift (Invariant A by construction)."""
    head = EntityHead(id=oqo.get_rows, text=oqo.get_rows.lower())
    where_keyword = ""
    where = None
    if oqo.filter_rows:
        where_keyword = " where "
        if len(oqo.filter_rows) == 1:
            where = _filter_node(oqo.filter_rows[0], top=True, resolver=resolver)
        else:
            children = [_filter_node(f, top=False, resolver=resolver)
                        for f in oqo.filter_rows]
            where = GroupNode(join="and", children=children, prefix="", suffix="",
                              joiner=" and ", meta=GroupMeta(implicit=True))

    directives = []
    if oqo.group_by:
        segs = []
        dims = []
        for i, g in enumerate(oqo.group_by):
            nm = _oql_field(g.column_id)[0]
            if i:
                segs.append(_seg("text", ", "))
            segs.append(_seg("column", nm, column_id=g.column_id))
            dims.append({"column_id": g.column_id, "column_display_name": nm})
        directives.append(GroupByDirective(
            prefix="group by ", segments=segs, meta=GroupByMeta(dimensions=dims)))
    if oqo.sort_by:
        segs = []
        keys = []
        for i, s in enumerate(oqo.sort_by):
            fld = _BY_COLUMN.get(s.column_id)
            nm = fld.oql if fld else s.column_id
            if i:
                segs.append(_seg("text", ", "))
            segs.append(_seg("column", nm, column_id=s.column_id))
            segs.append(_seg("text", " "))
            segs.append(_seg("keyword", s.direction))
            keys.append({"column_id": s.column_id, "order": s.direction,
                         "column_display_name": nm})
        primary = keys[0]
        directives.append(SortDirective(
            prefix="sort by ", segments=segs,
            meta=SortMeta(column_id=primary["column_id"], order=primary["order"],
                          column_display_name=primary["column_display_name"],
                          keys=keys)))
    if oqo.sample:
        segs = [_seg("value", str(oqo.sample), value=oqo.sample)]
        if oqo.seed is not None:
            segs.append(_seg("text", " seed "))
            segs.append(_seg("value", str(oqo.seed), value=oqo.seed))
        directives.append(SampleDirective(
            prefix="sample ", segments=segs, meta=SampleMeta(n=oqo.sample)))

    return OQLRenderTree(version="1.0", entity=head, where_keyword=where_keyword,
                         where=where, directives=directives)


# ---------------------------------------------------------------------------
# Width-aware canonical formatter (#376 Phase 2).
#
# `render()`/`render_tree()` are width-aware: a query whose one-line canonical
# form fits the target width renders flat (unchanged); a longer one is laid out
# multi-line by a recursive fits-or-explode pass (the Black model) over the SAME
# tree. Invariant A thus generalizes from "concatenated segments == oql" to
# "segments in reading order == oql, with newlines + indentation allowed between
# them": the whitespace-blind, trailing-comma-tolerant parser round-trips the
# multi-line form to the identical OQO. Layout is a pure function of
# (tree, width) -> idempotent. Spec: docs/oql-spec.md "Canonical formatting".
# ---------------------------------------------------------------------------
from query_translation.oql_render_tree import (  # noqa: E402
    _stringify_expr, _stringify_clause, _stringify_group, _stringify_directive,
)

FORMAT_WIDTH = 80   # soft target; nodes explode to keep flat forms within it
_INDENT = 2


def _leading_conn(group: GroupNode) -> str:
    """Connective that leads continuation operands of an exploded group
    (`"and "` / `"or "`); empty for a single-child wrapper (e.g. `not (...)`)."""
    j = group.joiner.strip()
    return f"{j} " if j else ""


def _split_list_clause(clause: ClauseNode):
    """If `clause` is a value-list clause (`… is any of (a, b, c)` /
    `… contains any of (…)`), return `(head, items, close)` where `head` ends
    with `"("`, `items` is the list of flat item strings, and `close == ")"`;
    else None. Splits on the engine's own structural segments (the literal
    `"("`, `", "`, `")"` text segments), so a `", "` inside a resolved
    `[display name]` (an `id` segment) is never mistaken for a separator."""
    segs = clause.segments
    open_idx = next((i for i, s in enumerate(segs)
                     if s.kind == "text" and s.text == "("), None)
    if open_idx is None or not (segs[-1].kind == "text" and segs[-1].text == ")"):
        return None
    head = "".join(s.text for s in segs[:open_idx + 1])
    items, cur = [], []
    for s in segs[open_idx + 1:-1]:
        if s.kind == "text" and s.text == ", ":
            items.append("".join(cur))
            cur = []
        else:
            cur.append(s.text)
    items.append("".join(cur))
    return head, items, ")"


def _fmt_list(head: str, items, indent: int, width: int) -> str:
    """Lay out an exploded value list. `indent` is the clause's own indent
    (where the closing `)` sits); items sit at `indent + _INDENT`. Every item
    carries a trailing comma (idempotence anchor + clean diffs; the parser
    tolerates it). <=8 items -> one per line; >8 -> fill/pack to `width`."""
    pad = " " * (indent + _INDENT)
    out = [head]
    if len(items) <= 8:
        out.extend(f"{pad}{it}," for it in items)
    else:
        line, empty = pad, True
        for it in items:
            piece = f"{it},"
            if not empty and len(line) + 1 + len(piece) > width:
                out.append(line)
                line, empty = pad, True
            line = f"{pad}{piece}" if empty else f"{line} {piece}"
            empty = False
        out.append(line)
    out.append(f"{' ' * indent})")
    return "\n".join(out)


def _fmt_clause(clause: ClauseNode, indent: int, col: int, width: int) -> str:
    flat = _stringify_clause(clause)
    if col + len(flat) <= width:
        return flat
    parts = _split_list_clause(clause)
    if parts is None:
        return flat   # an unbreakable clause (e.g. one long search term)
    head, items, _close = parts
    return _fmt_list(head, items, indent, width)


def _fmt_group(group: GroupNode, indent: int, col: int, width: int) -> str:
    flat = _stringify_group(group)
    if col + len(flat) <= width:
        return flat
    conn = _leading_conn(group)
    if group.prefix:
        # Parenthesized group: open bracket on the current line, every operand
        # on its own line one level deeper, closing bracket back at `indent`.
        child_indent = indent + _INDENT
        pad = " " * child_indent
        out = [group.prefix]
        for i, ch in enumerate(group.children):
            lead = "" if i == 0 else conn
            sub = _fmt_expr(ch, child_indent, child_indent + len(lead), width)
            out.append(f"{pad}{lead}{sub}")
        out.append(f"{' ' * indent}{group.suffix}")
        return "\n".join(out)
    # Bare group (top-level where body / implicit AND): the first operand
    # continues the current line; each subsequent operand starts a new line at
    # `indent`, led by the connective.
    out = []
    for i, ch in enumerate(group.children):
        if i == 0:
            out.append(_fmt_expr(ch, indent, col, width))
        else:
            sub = _fmt_expr(ch, indent, indent + len(conn), width)
            out.append(f"{' ' * indent}{conn}{sub}")
    return "\n".join(out)


def _fmt_expr(node: ExprNode, indent: int, col: int, width: int) -> str:
    if isinstance(node, ClauseNode):
        return _fmt_clause(node, indent, col, width)
    if isinstance(node, GroupNode):
        return _fmt_group(node, indent, col, width)
    return _stringify_expr(node)


def format_oql(tree: OQLRenderTree, width: int = FORMAT_WIDTH) -> str:
    """Lay out `tree` as canonical OQL within `width` columns. A query whose
    one-line form fits returns it unchanged; a longer one explodes top-down:
    the entity head, the `where` body, and each directive onto their own
    line(s)."""
    flat = stringify(tree)
    if len(flat) <= width:
        return flat
    lines = [tree.entity.text]
    if tree.where is not None:
        body = _fmt_expr(tree.where, _INDENT, len("where "), width)
        lines.append(f"where {body}")
    lines.extend(_stringify_directive(d) for d in tree.directives)
    return "\n".join(lines)


def render_tree(oqo: OQO, resolver=None):
    """OQO -> (canonical OQL string, oql_render tree). The string is the
    width-aware `format_oql(tree)`; for queries that fit one line it equals
    `stringify(tree)` (Invariant A), and the multi-line form still round-trips
    to the same OQO."""
    tree = _build_tree(oqo, resolver)
    return format_oql(tree), tree


def render(oqo: OQO, resolver=None) -> str:
    """OQO -> canonical OQL (width-aware multi-line when long; see `format_oql`).
    `resolver(value, column_id) -> name|None` (a 1-arg `resolver(value)` is also
    accepted) synthesizes `[display name]` annotations for opaque-ID / country
    columns."""
    return format_oql(_build_tree(oqo, resolver))
