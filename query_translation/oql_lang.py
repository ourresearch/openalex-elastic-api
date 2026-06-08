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
- `(...)` does double duty: boolean grouping of clauses AND a boolean group of
  search terms / values (`title contains (a or b)`, `country is (us or uk)`). A
  list of 2+ bare terms/values must be parenthesized; a single one may be bare.
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
from query_translation.oqo import (  # noqa: E402
    OQO, LeafFilter, BranchFilter, FilterType, GroupBy, SortBy, CURLY_DQUOTE_MAP)


# ---------------------------------------------------------------------------
# Diagnostics — a named code + human message + fix-it for every error/hint.
# Codes are the language-agnostic contract (charter decision 5); prose localizes.
# The vocabulary (every code + its severity / summary / default fix-it) and the
# carriers (OQLError, OQLHint) live in the shared `diagnostics` registry so the
# parser, the OQO validator, and the editor can't drift (oxjob #363). Re-exported
# here for backwards compatibility (`from ...oql_lang import OQLError` still works).
# Raises go through `oql_error(...)`, which validates the code against the registry
# and fills in the canonical fix-it when a site doesn't supply one.
# ---------------------------------------------------------------------------
from query_translation.diagnostics import OQLError, OQLHint, oql_error  # noqa: E402


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
    is_float: bool = False  # num kind: True = decimals allowed (fwci); False = integer
                            # (year, count). Integer fields collapse a strict bound
                            # PAIR to an inclusive range via ±1 (`>42 and <100` -> 43-99).


_FIELDS: List[Tuple[List[str], Field]] = []  # (alias-spellings, Field)


def _f(oql, column, kind, aliases=(), bool_true="", bool_false="",
       casing=None, resolves_name=None, is_float=False):
    if casing is None:
        casing = "lower" if kind == "enum" else ""
    if resolves_name is None:
        resolves_name = (kind == "id")
    fld = Field(column=column, kind=kind, oql=oql, bool_true=bool_true,
                bool_false=bool_false, casing=casing, resolves_name=resolves_name,
                is_float=is_float)
    spellings = [oql] + list(aliases)
    _FIELDS.append(([s.lower() for s in spellings], fld))
    return fld


def _canon_value_case(value, fld: "Field"):
    """Apply the column's cosmetic value casing (never touches col_… refs)."""
    if not isinstance(value, str) or value.startswith("col_") or not fld.casing:
        return value
    return value.lower() if fld.casing == "lower" else value.upper()


# --- search fields (column is the *base*; .search suffix added per mode) ---
# `title.search` is a GUI/docs alias for display_name.search (facetConfigs.js: "Alias for
# display_name.search to support URLs like /works?filter=title.search:ai"); the elastic-api
# honors it as a filter, so OQL must resolve it too or a shared "Title"-scope URL errors in
# the editor with `unknown field "title.search"` (oxjob #397).
_f("title", "display_name", "search", aliases=["display_name.search", "display_name", "title.search"])
# Render word "title/abstract" is the registry's canonical display_name (#381 Phase 5);
# the old "title & abstract" spelling stays a parse alias for back-compat.
_f("title/abstract", "title_and_abstract", "search",
   aliases=["title & abstract", "title and abstract", "title_and_abstract.search", "title_and_abstract", "title&abstract"])
_f("abstract", "abstract", "search", aliases=["abstract.search"])
# "full text" is the canonical broad full-text scope: title + abstract + full text
# (oxjob #374; render word = the registry display_name, #381 Phase 5). All broad-search
# spellings — including the one-word "fulltext", the old "anywhere" word, and the
# deprecated "default.search" param name — fold in here and emit fulltext.search, so OQL
# never produces the deprecated default.search key. (Stray default.search columns from
# external URL→OQO still render to "full text" via the _BY_COLUMN alias below.)
_f("full text", "fulltext", "search",
   aliases=["fulltext.search", "fulltext", "anywhere", "any field", "default", "default.search"])
_f("raw affiliation", "raw_affiliation_strings", "search",
   aliases=["raw_affiliation_strings.search", "affiliation", "raw affiliation string"])
_f("byline", "raw_author_name", "search",
   aliases=["raw_author_name.search", "raw author name"])
_f("institution name", "institutions.display_name", "search",
   aliases=["institutions.display_name.search"])
# Free-text search within a work's curated keywords only (engine param keyword.search →
# keywords.display_name). Distinct from `topic` (an entity id): keywords are short curated
# phrases searched as text. Engine recall is narrow (matches single curated tokens; common
# multi-word terms return 0), but `?filter=keyword.search:…` is a real working oxurl, so
# OQL must be able to represent it. (oxjob #363 discovery loop run #1)
_f("keyword", "keyword", "search", aliases=["keyword.search"])

# --- numeric ---
_f("year", "publication_year", "num", aliases=["publication_year"])
# Render word "citation count" = the registry display_name (#381 v1.5.0): the COUNT,
# kept distinct from the cited_by/cites relationship filters. Old "citations" → alias.
_f("citation count", "cited_by_count", "num", aliases=["citations", "cited_by_count", "cited by count"])
_f("FWCI", "fwci", "num", aliases=["fwci"], is_float=True)
# The work's citation count normalized by subfield + year, as a percentile (0-100).
# Render word = registry display_name "citation percentile by subfield" (#363 case 4).
_f("citation percentile by subfield", "citation_normalized_percentile.value", "num",
   aliases=["citation_normalized_percentile.value"], is_float=True)

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
# Full text available in some open repository (engine open_access.any_repository_has_fulltext).
# Booleans render via their phrasing (gate-exempt from the registry display_name). (#363 case 6)
# The bool clause parser maps the phrase AFTER the "it's"/"it has" prefix back to
# a field via its aliases, so the post-prefix phrasing is registered as an alias
# (so the rendered bool_true round-trips). Booleans are gate-exempt, so the extra
# spellings are free.
_f("has repository fulltext", "open_access.any_repository_has_fulltext", "bool",
   aliases=["open_access.any_repository_has_fulltext", "fulltext in a repository"],
   bool_true="it has fulltext in a repository", bool_false="it doesn't have fulltext in a repository")
# Citation-percentile band flags (subfield+year normalized). (#363 case 4 siblings)
_f("in top 1% by citations", "citation_normalized_percentile.is_in_top_1_percent", "bool",
   aliases=["citation_normalized_percentile.is_in_top_1_percent", "in the top 1% by citations"],
   bool_true="it's in the top 1% by citations", bool_false="it's not in the top 1% by citations")
_f("in top 10% by citations", "citation_normalized_percentile.is_in_top_10_percent", "bool",
   aliases=["citation_normalized_percentile.is_in_top_10_percent", "in the top 10% by citations"],
   bool_true="it's in the top 10% by citations", bool_false="it's not in the top 10% by citations")

# --- ids (entity references) ---
_f("institution", "authorships.institutions.lineage", "id",
   aliases=["authorships.institutions.lineage"])
_f("author", "authorships.author.id", "id", aliases=["authorships.author.id"])
_f("source", "primary_location.source.id", "id", aliases=["primary_location.source.id"])
_f("topic", "primary_topic.id", "id", aliases=["primary_topic.id"])
_f("topics", "topics.id", "id", aliases=["topics.id"])
_f("funder", "funders.id", "id", aliases=["funders.id", "grants.funder"])
# Publisher of the work's primary source (engine param primary_location.source.publisher_lineage,
# a P-id; lineage so a parent publisher matches its imprints). Mirrors `funder`: an entity-id
# reference, name-resolved via the publishers namespace. (oxjob #363 discovery loop run #1)
_f("publisher", "primary_location.source.publisher_lineage", "id",
   aliases=["primary_location.source.publisher_lineage", "primary_location.source.host_organization_lineage"])
# Render word "SDG" = the registry display_name (#381 Phase 5: acronym made canonical
# everywhere). Long forms stay parse aliases.
_f("SDG", "sustainable_development_goals.id", "id",
   aliases=["sustainable_development_goals.id", "sustainable development goal", "sustainable development goals", "sdg"])
_f("last known institution", "last_known_institutions.id", "id",
   aliases=["last_known_institutions.id"])
_f("domain", "domain.id", "id", aliases=["domain.id"])
_f("field", "primary_topic.field.id", "id", aliases=["primary_topic.field.id"])
# subfield of the work's primary topic (topic hierarchy: domain > field > subfield > topic).
# Was missing while its siblings field/domain/topic were registered (oxjob #363 discovery run #2);
# render word = registry display_name "subfield"; name-resolved via the native subfields namespace.
_f("subfield", "primary_topic.subfield.id", "id", aliases=["primary_topic.subfield.id"])
_f("openalex id", "ids.openalex", "id", aliases=["ids.openalex"])
# Citation relationships to a specific work (W-id; resolves the work's title).
# Render words = registry display_names "cited by" / "cites" (#363 case 7).
# cited_by:W = works in W's reference list ("cited by" W); cites:W = works citing W.
_f("cited by", "cited_by", "id", aliases=["cited_by"])
_f("cites", "cites", "id", aliases=["cites"])

# --- collection (same-type membership) ---
# The same-type `collection:` filter: "this row's entity is a member of Collection
# col_…". Surfaced as `<subject> is in collection col_…` where the subject is the
# queried entity (works-centric registry → "work"). Cross-type membership reuses the
# referenced entity's own column (e.g. `country`/`institution`/`author`) — no separate
# field. kind "collection" parses a bare col_… scalar (no name resolution). (oxjob #363)
_f("work", "collection", "collection", aliases=["works"], resolves_name=False)

# --- enums (slug values) ---
_f("type", "type", "enum", aliases=[])
# Render word "open access status" = the registry display_name (#381 Phase 5); the
# greedy field matcher prefers it over the 2-word "open access" bool when "status"
# follows. Old "OA status" → parse alias.
_f("open access status", "open_access.oa_status", "enum", aliases=["OA status", "open_access.oa_status", "oa status"])
# Country codes: ISO uppercase canonical + resolve a [display name] (Germany, not de).
_f("country", "authorships.countries", "enum", aliases=["authorships.countries"],
   casing="upper", resolves_name=True)
_f("country code", "country_code", "enum", aliases=["country_code"],
   casing="upper", resolves_name=True)
_f("author country", "last_known_institutions.country_code", "enum",
   aliases=["last_known_institutions.country_code"], casing="upper", resolves_name=True)
# Languages resolve a [display name] (English, not en) from config/languages.yaml,
# like countries — a closed code vocabulary, not a "super obvious" enum. (oxjob #363 case 5)
_f("language", "language", "enum", aliases=[], resolves_name=True)
# The source's type (journal / conference / repository / ebook platform / book series /
# metadata / other). Render word = the engine registry display_name `source type`
# (`core/display_names.py`). Slug enum; multi-word values like "ebook platform" are
# valid atoms. Distinct from `type` (the WORK's type, column `type`). (oxjob #363)
_f("source type", "primary_location.source.type", "enum",
   aliases=["primary_location.source.type", "source.type"])

# --- literal strings ---
_f("DOI", "doi", "string", aliases=["doi"])
_f("ORCID", "authorships.author.orcid", "string", aliases=["authorships.author.orcid", "author orcid"])
# The work's journal, by ISSN (engine param primary_location.source.issn; accepts ISSN-L or
# any of a source's ISSNs). Literal string like DOI/ORCID — no name resolution. WoS `IS=`,
# Scopus `ISSN()`. (oxjob #363 discovery loop run #1)
_f("ISSN", "primary_location.source.issn", "string",
   aliases=["issn", "primary_location.source.issn", "source.issn"])

# --- oxjob #402 friendly-name audit (long-tail GUI/docs columns) ---
# Front-B-only batch: every render word below already equals the column's registry
# `display_name` (no core/display_names.py change, no PROPERTIES_VERSION bump). The
# raw column_id stays a structural alias so the #363 input-alias fallback drops it.

# distinct-count metrics (kind num; registry display_names already clean).
_f("reference count", "referenced_works_count", "num", aliases=["referenced_works_count"])
_f("institutions count", "institutions_distinct_count", "num", aliases=["institutions_distinct_count"])
_f("countries count", "countries_distinct_count", "num", aliases=["countries_distinct_count"])

# DOI prefix match (engine param doi_starts_with; literal string, no resolution).
_f("DOI prefix", "doi_starts_with", "string", aliases=["doi_starts_with"])

# Corresponding-author / -institution entity-id filters (name-resolved via the
# authors / institutions namespaces, like `author` / `institution`).
_f("corresponding author", "corresponding_author_ids", "id",
   aliases=["corresponding_author_ids"])
_f("corresponding institution", "corresponding_institution_ids", "id",
   aliases=["corresponding_institution_ids"])

# Bibliographic coordinates (kind string — volumes/issues/pages are free-text
# labels, e.g. "42", "S1", "iv"). PROPERTIES_VERSION 1.9.0 curated the registry
# display_names from the raw "biblio volume"/… humanized ids.
_f("volume", "biblio.volume", "string", aliases=["biblio.volume"])
_f("issue", "biblio.issue", "string", aliases=["biblio.issue"])
_f("first page", "biblio.first_page", "string", aliases=["biblio.first_page"])
_f("last page", "biblio.last_page", "string", aliases=["biblio.last_page"])

# Legacy / external work ids (kind string — literal, no name resolution).
# Registry display_names curated in 1.9.0 from raw "ids mag"/"ids pmid"/"ids pmcid".
_f("MAG ID", "ids.mag", "string", aliases=["ids.mag"])
_f("PMID", "ids.pmid", "string", aliases=["ids.pmid"])
_f("PMCID", "ids.pmcid", "string", aliases=["ids.pmcid"])

# APC (article processing charge). Only the USD estimated-paid column is curated —
# its registry display_name is already clean ("estimated APC paid", and it's the one
# faceted in the GUI), so this is Front-B only (no display_name change, no version
# bump). It's a currency amount (USD, may be fractional) → num/is_float. The other 7
# apc columns (apc_list.{value,value_usd,currency,provenance}, apc_paid.{value,
# currency,provenance}) are deliberately LEFT OUT OF SCOPE per Jason (2026-06-08):
# native-currency duplicates + provenance/currency metadata aren't worth an OQL
# surface; they stay on the #363 raw-key input-alias fallback as documented residue.
_f("estimated APC paid", "apc_paid.value_usd", "num",
   aliases=["apc_paid.value_usd"], is_float=True)

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


def is_integer_column(column_id) -> bool:
    """True for a numeric column whose values are whole numbers (year,
    cited_by_count) — distinct from a float num column (fwci). Used by the OQO
    canonicalizer to collapse a strict integer bound PAIR to an inclusive range
    (`>42 and <100` -> `>=43 and <=99` -> 43-99). (oxjob #363)"""
    fld = _BY_COLUMN.get(column_id)
    return bool(fld and fld.kind == "num" and not fld.is_float)


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
    # Coerce curly/smart double-quotes to ASCII (1:1, length-preserving so token
    # positions stay exact). Multi-quote runs (`"""x"""`) are collapsed
    # position-preservingly in the STRING branch below. (oxjob #363)
    s = s.translate(CURLY_DQUOTE_MAP)
    toks: List[Tok] = []
    i, n = 0, len(s)
    while i < n:
        c = s[i]
        if c in ' \t\n':
            i += 1
            continue
        if c == '"':
            # Collapse a run of 2+ opening/closing quotes to a single delimiter,
            # so `"""universiteit maastricht"""` lexes as ONE string (the literal
            # the user meant) rather than three. Positions reference the ORIGINAL
            # offsets (no rewrite), so diagnostics stay accurate. (oxjob #363)
            start = i
            while i + 1 < n and s[i + 1] == '"':
                i += 1                       # skip extra opening quotes
            j = s.find('"', i + 1)
            if j == -1:
                raise oql_error("OQL_UNTERMINATED_STRING",
                               f'unterminated string starting at position {start}',
                               'add a closing double-quote (")', start)
            content = s[i + 1:j]
            i = j
            while i + 1 < n and s[i + 1] == '"':
                i += 1                       # skip extra closing quotes
            toks.append(Tok("STRING", content, start))
            i += 1
            continue
        if c == '[':
            j = s.find(']', i + 1)
            if j == -1:
                raise oql_error("OQL_UNTERMINATED_ANNOTATION",
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
# Numeric values + ranges (oxjob #363). A num field's value is either a single
# number or a bounded/open range written with a hyphen, mirroring the OpenAlex
# URL range form:
#     2019-2023   -> >= 2019  AND  <= 2023   (closed range)
#     2019-       -> >= 2019                  (open lower)
#     -2023       ->            <= 2023       (open upper)
# A leading hyphen is always the open-upper form (never a negative number): no
# num field (year / count / fwci) takes negatives, so the reading is unambiguous.
_NUM_RE = re.compile(r"\d+(?:\.\d+)?$")
_RANGE_RE = re.compile(r"^(?P<lo>\d+(?:\.\d+)?)?-(?P<hi>\d+(?:\.\d+)?)?$")


def _coerce_number(val: str, fld: "Field", pos):
    """Parse a single numeric atom to int (or float for is_float fields)."""
    try:
        return int(val)
    except ValueError:
        if fld.is_float:
            try:
                return float(val)
            except ValueError:
                pass
    raise oql_error("OQL_BAD_NUMBER",
                   f'"{val}" is not a number for "{fld.oql}"', "", pos)


def _parse_num_range(val: str, fld: "Field", pos):
    """If `val` is a hyphen range for a num field, return a list of bound
    LeafFilters (>= lo, <= hi); else None. Raises OQL_BAD_NUMBER on a malformed
    side (e.g. `2019-abc`)."""
    m = _RANGE_RE.match(val)
    if not m:
        return None
    lo, hi = m.group("lo"), m.group("hi")
    if lo is None and hi is None:
        return None  # a bare "-" is not a range
    leaves = []
    if lo is not None:
        leaves.append(LeafFilter(fld.column, _coerce_number(lo, fld, pos), ">="))
    if hi is not None:
        leaves.append(LeafFilter(fld.column, _coerce_number(hi, fld, pos), "<="))
    return leaves


# ---------------------------------------------------------------------------
# Shared greedy matchers — the SINGLE source of truth for how the grammar
# recognizes a field and an operator. Pure, index-based, non-raising: they take a
# token list + a start index and return (match, …) or None without mutating state.
#
# Both the fail-fast parser (`_Parser`, below) and the non-raising editor-context
# walker (`oql_context.py`, oxjob #357) call these, so the editor can never offer or
# accept a field/operator the parser would reject — previously `oql_context` kept a
# *parallel* reimplementation that had already drifted (it didn't recognize the
# `is in collection` operator). oxjob #363, charter decision 13 ("the real lever is the
# framework-independent semantic layer"). `test_parse_context.py` asserts the two call
# sites agree.
# ---------------------------------------------------------------------------
def match_field(toks: List[Tok], i: int) -> Optional[Tuple[str, "Field", int]]:
    """Greedy longest field-alias match (up to 4 words) at ``toks[i]``.
    Returns ``(spelling, Field, n_tokens)`` or ``None``."""
    best: Optional[Field] = None
    best_len = 0
    parts: List[str] = []
    for k in range(0, 4):
        t = toks[i + k] if i + k < len(toks) else None
        if not t or t.kind != "WORD":
            break
        parts.append(t.val)
        key = " ".join(parts).lower()
        if key in _ALIAS:
            best = _ALIAS[key]
            best_len = k + 1
    if best is None:
        return None
    spelling = " ".join(toks[i + k].val for k in range(best_len))
    return spelling, best, best_len


# --- Raw registry column_id fallback (oxjob #363) -------------------------
# OQL's curated `_FIELDS` give every common filter a friendly name; the raw
# oxurl column_id of a *curated* field already parses (it's listed as an alias).
# The gap was the long tail of columns with NO curated surface (e.g.
# `apc_paid.value_usd`, `biblio.volume`, `ids.pmid`): submitting their raw key —
# which an oxurl-fluent user, or a round-tripped render of an unsurfaced column,
# naturally does — 400'd "unknown field". So accept those raw column_ids as input
# aliases, synthesizing a Field from the registry's operator metadata. The render
# stays canonical (an uncurated column renders its raw id, which round-trips
# through this same fallback).
#
# Scope = GUI/docs parity, NOT the full registry (Jason, 2026-06-08): only columns
# that are GUI-faceted or documented (`INPUT_ALIAS_COLUMNS`) — accepting the whole
# 207-column registry would surface internal / half-baked / redundant fields that
# only confuse people. Built lazily + defensively so `oql_lang` stays importable
# in lightweight contexts without the engine properties registry.
_REGISTRY_FALLBACK_CACHE: Optional[Dict[str, "Field"]] = None


def _build_registry_fallback() -> Dict[str, "Field"]:
    try:
        from core.properties import get_entity_properties
        from query_translation.input_alias_columns import INPUT_ALIAS_COLUMNS
        cols = get_entity_properties("works")
    except Exception:
        return {}
    out: Dict[str, Field] = {}
    for cid, prop in cols.items():
        key = cid.lower()
        if key in _ALIAS:
            continue                     # already curated (or its raw id is an alias)
        if cid not in INPUT_ALIAS_COLUMNS:
            continue                     # not GUI-faceted / documented -> don't surface it
        ops = tuple(getattr(prop, "operators", []) or [])
        if "search" in ops or "collection" in ops:
            # search columns are mode-encoded (.search/.search.exact) — expressed
            # via the curated friendly fields + quoting, not a raw-id leaf; the
            # `collection` column is curated. Skip both.
            continue
        kind = "num" if "range" in ops else "string"   # 'range' => comparisons/ranges; else verbatim value
        out[key] = Field(column=cid, kind=kind, oql=cid, casing="",
                         resolves_name=False, is_float=(kind == "num"))
    return out


def _registry_fallback_field(word: str) -> Optional["Field"]:
    """The synthetic Field for a raw registry column_id (case-insensitive), or
    None if `word` isn't a known works column (or the registry is unavailable)."""
    global _REGISTRY_FALLBACK_CACHE
    if _REGISTRY_FALLBACK_CACHE is None:
        _REGISTRY_FALLBACK_CACHE = _build_registry_fallback()
    return _REGISTRY_FALLBACK_CACHE.get(word.lower())


def match_operator(toks: List[Tok], i: int) -> Optional[Tuple[str, int, bool, bool]]:
    """Greedy operator match at ``toks[i]``.

    Returns ``(op, n_tokens, complete, opens_list)`` or ``None`` if the token can't
    begin an operator. For every ``complete=True`` result, ``n_tokens``/``op`` are
    exactly what the fail-fast parser consumes/returns. ``complete=False`` means a
    multi-word operator is still being typed (e.g. ``is any`` without ``of``) — the
    editor treats that as "keep typing"; the parser falls back to the shorter complete
    operator (``is``) or raises. ``opens_list`` is True for the value-list openers
    (``is any of`` / ``is not any of`` / ``is in`` / ``is not in``).
    """
    if i >= len(toks):
        return None
    t = toks[i]
    if t.kind == "OP":  # > >= < <=
        return t.val, 1, True, False
    if t.kind != "WORD":
        return None

    def w(k: int) -> Optional[str]:
        tk = toks[i + k] if i + k < len(toks) else None
        return tk.val.lower() if tk and tk.kind == "WORD" else None

    w0 = w(0)
    if w0 == "contains":
        return "contains", 1, True, False
    if w0 == "is":
        if w(1) == "similar":
            if w(2) == "to":
                return "similar", 3, True, False
            return "similar", 2, False, False        # `is similar` — still typing
        if w(1) == "not":
            if w(2) == "any":
                if w(3) == "of":
                    return "nin", 4, True, True
                return "nin", 3, False, True          # `is not any` — typing
            if w(2) == "in":
                # `is not in collection` MUST precede the bare `is not in`
                if w(3) == "collection":
                    return "nincoll", 4, True, False
                return "nin", 3, True, True            # `is not in` == "is not any of"
            return "isnot", 2, True, False            # `is not` (scalar)
        if w(1) == "any":
            if w(2) == "of":
                return "in", 3, True, True
            return "in", 2, False, True               # `is any` — typing
        if w(1) == "in":
            if w(2) == "collection":
                return "incoll", 3, True, False
            return "in", 2, True, True                # `is in` == "is any of"
        return "is", 1, True, False
    if w0 in ("does", "doesn't", "doesnt"):
        j = 1 if w(1) == "not" else 0
        if w(1 + j) == "contain":
            return "ncontains", 2 + j, True, False
        return "ncontains", 1 + j, False, False        # `does not` — typing
    return None


# ---------------------------------------------------------------------------
# Editor-context grammar-state categories (oxjob #363, charter decision 15).
# These are the canonical strings the dual-mode parser reports at a cursor; the
# editor presentation layer (`oql_context.py`) re-exports them and maps them to
# suggestion lists. Defined HERE so the parser is the single source of grammar truth.
# ---------------------------------------------------------------------------
CTX_ENTITY = "entity"
CTX_FIELD = "field"
CTX_OPERATOR = "operator"
CTX_VALUE = "value"
CTX_CONNECTIVE = "connective"
CTX_DIRECTIVE = "directive-keyword"
CTX_END = "annotation-or-end"
CTX_NONE = "none"


class _CtxFound(Exception):
    """Internal control-flow signal (context mode only): the parser reached the
    cursor (end of the truncated prefix) at an expect-point and recorded what the
    grammar wants there. Never raised in strict mode, never escapes the engine."""


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------
class _Parser:
    def __init__(self, toks: List[Tok]):
        self.toks = toks
        self.i = 0
        self.hints: List[OQLHint] = []
        # --- dual-mode (editor-context) state (oxjob #363, decision 15) ---
        # `_ctx_mode` is False for all production parsing, so every `_want(...)`
        # call and every `if self._ctx_mode` branch below is an inert no-op on the
        # strict path — strict behavior is byte-identical (locked by tests/oql).
        self._ctx_mode = False
        self._ctx = None          # (category, payload) recorded at the cursor
        self._entity = None       # resolved get_rows entity (for the context reply)
        self._cur_fld = None      # field of the clause currently being parsed
        self._in_list = False     # are we inside a parenthesized value list?
        self._directive = None    # "sort" / "group" when inside a directive
        # --- dual-mode (editor-recover) state (oxjob #363, decision 15) ---
        # `_recover_mode` is the second, INDEPENDENT dual mode (never on at the same
        # time as `_ctx_mode`). False for all production parsing, so the recover
        # branches below are inert no-ops on the strict path — strict behavior is
        # byte-identical (locked by tests/oql). When True (the editor `/validate`
        # path via `parse_collecting`), a clause-level `OQLError` is recorded into
        # `_diagnostics` and the parser SYNCHRONIZES to the next safe boundary and
        # keeps going, so the editor can squiggle the WHOLE doc instead of just the
        # first error.
        self._recover_mode = False
        self._diagnostics: List[OQLError] = []

    # -- editor-context hook (no-op in strict mode) --
    def _want(self, category, **payload):
        """Record "the grammar expects <category> here" when the cursor (= end of
        the truncated prefix) sits at this expect-point. No-op unless we're in
        context mode AND out of tokens AND nothing deeper already claimed the spot
        (innermost wins). Raises `_CtxFound` to unwind straight to
        `parse_for_context`. On the strict path this returns immediately."""
        if self._ctx_mode and self._ctx is None and self.peek() is None:
            self._ctx = (category, dict(payload))
            raise _CtxFound()

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
        self._entity = entity
        filters: List[FilterType] = []
        sort_by: List[SortBy] = []
        group_by: List[GroupBy] = []
        sample = None
        seed = None
        self._skip_annot()
        # After a complete entity with nothing typed yet, the cursor sits in the
        # "where / sort by / group by / sample / end" slot.
        self._want(CTX_DIRECTIVE)
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
                if self._ctx_mode:
                    # trailing junk after a complete query: offer directives / end
                    self._ctx = (CTX_END, {})
                    raise _CtxFound()
                raise oql_error("OQL_TRAILING_TOKENS",
                               f'unexpected text near "{t.val}" (position {t.pos})',
                               'queries are: <entity> [where <conditions>] [sort by ...] '
                               '[group by ...] [sample N]', t.pos)
        return OQO(get_rows=entity, filter_rows=filters, sort_by=sort_by,
                   group_by=group_by, sample=sample, seed=seed)

    # -- editor-context entry (dual mode; oxjob #363, decision 15) --
    def parse_for_context(self) -> dict:
        """Run the SAME grammar over a prefix in context mode and report what the
        grammar expects at the cursor (= end of the tokens). Returns
        ``{"category", "entity", **payload}``. Never raises: a `_CtxFound` carries
        the recorded expectation; a real OQLError in the prefix degrades to the
        best expectation recorded so far, else END/NONE. This is what lets the
        editor's `oql_context` retire its parallel grammar-state walker."""
        self._ctx_mode = True
        try:
            self.parse()
            # Parsed a complete query with no pending expectation: the cursor is
            # past a finished query — offer directives / end.
            return {"category": CTX_END, "entity": self._entity}
        except _CtxFound:
            cat, payload = self._ctx
            return {"category": cat, "entity": self._entity, **payload}
        except OQLError:
            # A genuine error sits before the cursor. Prefer any expectation we
            # already recorded; otherwise we can't classify (suppressed).
            if self._ctx is not None:
                cat, payload = self._ctx
                return {"category": cat, "entity": self._entity, **payload}
            return {"category": CTX_NONE, "entity": self._entity}

    # -- editor-recover entry (dual mode; oxjob #363, decision 15) --
    def parse_collecting(self) -> Tuple[Optional[OQO], List[OQLError]]:
        """Run the SAME grammar over the full input collecting ALL clause-level
        diagnostics instead of failing on the first. Returns
        ``(oqo_or_None, diagnostics)``.

        Recovery happens at two boundaries (charter decision 15): each
        ``_operand()`` and each value-list element catches its ``OQLError``, records
        it, and synchronizes to the next safe boundary so parsing of the rest of the
        query resumes. An error OUTSIDE a recoverable boundary (entity, a directive,
        trailing tokens, an unbalanced paren at the top level) is recorded as the
        terminal diagnostic. The returned OQO is best-effort (it may contain recovery
        placeholders) and is meant only for the caller to know whether the parse was
        clean — when ``diagnostics`` is non-empty the editor uses the diagnostics, not
        the OQO. Strict ``parse()`` never enters this mode."""
        self._recover_mode = True
        oqo = None
        try:
            oqo = self.parse()
        except OQLError as e:
            self._diagnostics.append(e)
        return oqo, list(self._diagnostics)

    def _recovery_placeholder(self) -> LeafFilter:
        """A throwaway leaf inserted where a clause failed to parse, so the enclosing
        expression keeps a valid shape during recovery. Never reaches execution: the
        editor surfaces diagnostics, not this OQO."""
        return LeafFilter(column_id="__recovery_error__", value=None, operator="is")

    def _operand(self) -> FilterType:
        """Parse one operand. In recover mode an ``OQLError`` is recorded and we
        synchronize to the next clause boundary, returning a placeholder so the
        enclosing ``_parse_expr`` keeps its shape; strict mode just delegates (the
        recover branch is dead code on the strict path)."""
        if not self._recover_mode:
            return self._parse_operand()
        start_i = self.i
        try:
            return self._parse_operand()
        except OQLError as e:
            self._diagnostics.append(e)
            self._synchronize()
            if self.i == start_i and self.peek() is not None:
                self.next()  # guarantee forward progress -> no infinite loop
            return self._recovery_placeholder()

    def _synchronize(self):
        """Recovery: advance to the next safe boundary so clause parsing can resume
        after an error — a top-level connective (and/or), a directive keyword
        (sort/group/sample), the start of a new field clause (so an
        adjacency-after-error still gets reported, not swallowed), a closing paren, a
        semicolon, or end. Parens are depth-tracked so a half-parsed group doesn't let
        recovery escape it. Forward progress at the error site is guaranteed by the
        caller (`_operand` force-advances when synchronize consumes nothing AND the
        operand consumed nothing), so a clause-start sitting right at the cursor is
        safe to stop on."""
        depth = 0
        while True:
            t = self.peek()
            if t is None:
                return
            if t.kind == "LP":
                depth += 1
                self.next()
                continue
            if t.kind == "RP":
                if depth == 0:
                    return  # let the enclosing group's _expect_rp consume it
                depth -= 1
                self.next()
                continue
            if depth == 0:
                if t.kind == "SEMI":
                    return
                if t.kind == "WORD" and t.val.lower() in _CONNECTIVES:
                    return
                if t.kind == "WORD" and t.val.lower() in ("sort", "group", "sample"):
                    return
                # A new field clause begins here (e.g. `... year is abc title is x`):
                # stop so the connective loop reports the missing AND/OR rather than
                # swallowing the clause.
                if self._starts_new_clause(0):
                    return
            self.next()

    def _parse_entity(self) -> str:
        # Greedy longest match against ENTITY_TYPES (handles "source types").
        self._want(CTX_ENTITY)
        t = self.peek()
        if t is None or t.kind != "WORD":
            raise oql_error("OQL_MISSING_ENTITY",
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
        if self._ctx_mode:
            # a leading word that isn't (yet) a known entity is still the entity slot
            self._ctx = (CTX_ENTITY, {})
            raise _CtxFound()
        raise oql_error("OQL_UNKNOWN_ENTITY",
                       f'unknown entity type "{t.val}"',
                       f'use one of: works, authors, institutions, sources, ...', t.pos)

    # -- boolean expression with single-connective-per-level enforcement --
    def _parse_expr(self, top=False) -> FilterType:
        operands = [self._operand()]
        conns: List[str] = []
        while True:
            self._skip_annot()
            # A complete operand with the cursor right after it: the slot wants a
            # connective (and / or) — or a directive / closing paren / end.
            self._want(CTX_CONNECTIVE)
            t = self.peek()
            if t is None or t.kind in ("RP", "SEMI"):
                break
            if t.kind == "WORD" and t.val.lower() == "not":
                # NOT at a connective position means "a NOT b" with no AND/OR.
                if self._recover_mode:
                    self._diagnostics.append(self._adjacency_err(t))
                    operands.append(self._operand())  # recover: treat as implicit AND
                    continue
                self._adjacency_error(t)
            if t.kind == "WORD" and t.val.lower() in _CONNECTIVES:
                conns.append(t.val.lower())
                self.next()
                operands.append(self._operand())
                continue
            # directive keywords end the where-expression
            if t.kind == "WORD" and t.val.lower() in ("sort", "group", "sample"):
                break
            # anything else with no connective = implicit adjacency
            if self._recover_mode:
                self._diagnostics.append(self._adjacency_err(t))
                operands.append(self._operand())  # recover: treat as implicit AND
                continue
            self._adjacency_error(t)
        if not conns:
            return operands[0]
        if len(set(conns)) > 1:
            first = self.toks[0]
            if self._recover_mode:
                # Don't abort the whole parse for a mixed-bool ambiguity: record it
                # and pick the first connective so recovery keeps the tree's shape.
                self._diagnostics.append(oql_error(
                    "OQL_MIXED_BOOL_NEEDS_PARENS",
                    "mixed AND/OR at one level is ambiguous — add parentheses",
                    'group explicitly, e.g. "a and (b or c)" or "(a and b) or c"',
                    first.pos))
            else:
                raise oql_error(
                    "OQL_MIXED_BOOL_NEEDS_PARENS",
                    "mixed AND/OR at one level is ambiguous — add parentheses",
                    'group explicitly, e.g. "a and (b or c)" or "(a and b) or c"',
                    first.pos)
        join = conns[0]
        return BranchFilter(join=join, filters=operands)

    def _adjacency_error(self, t: Tok):
        raise self._adjacency_err(t)

    def _adjacency_err(self, t: Tok) -> OQLError:
        return oql_error("OQL_IMPLICIT_ADJACENCY",
                        f'two conditions with no AND/OR between them (near "{t.val}")',
                        'insert an explicit AND or OR', t.pos)

    def _parse_operand(self) -> FilterType:
        self._skip_annot()
        # An empty operand slot (start of conditions, or just after "(" / a
        # connective) expects a field clause.
        self._want(CTX_FIELD)
        t = self.peek()
        if t is None:
            raise oql_error("OQL_EMPTY", "expected a condition", "")
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
        if t is not None and t.kind == "COMMA":
            raise oql_error("OQL_COMMA_IN_GROUP",
                           "items in a (…) group are separated by 'or'/'and', "
                           "not commas",
                           "replace the comma with 'or' (or 'and')", t.pos)
        if t is None or t.kind != "RP":
            raise oql_error("OQL_UNBALANCED_PARENS", "missing a closing parenthesis",
                           "add a )", t.pos if t else None)
        self.next()

    # -- clauses --
    def _parse_clause(self) -> FilterType:
        self._skip_annot()
        # boolean human form: it's / its / it
        if self.word_is("it's", "its", "it"):
            return self._parse_boolean_clause()
        field, fld = self._parse_field()
        self._cur_fld = fld
        # a complete field with the cursor right after it -> operator slot
        self._want(CTX_OPERATOR, fld=fld)
        op = self._parse_operator()
        if fld.kind == "search":
            if op == "similar":
                return self._parse_semantic(fld)
            if op not in ("contains", "ncontains"):
                raise oql_error("OQL_BAD_OPERATOR_FOR_FIELD",
                               f'search field "{field}" needs "contains" (not "{op}")',
                               'use: <field> contains <terms>')
            tree = self._parse_search_value(fld.column)
            if op == "ncontains":
                tree = _negate(tree)
            return tree
        # non-search
        if op in ("contains", "ncontains", "similar"):
            raise oql_error("OQL_BAD_OPERATOR_FOR_FIELD",
                           f'field "{field}" does not support "{op}"',
                           'use "is" / a comparison')
        return self._parse_value_clause(field, fld, op)

    def _parse_field(self) -> Tuple[str, Field]:
        # an empty / partially-typed field slot at the cursor
        self._want(CTX_FIELD)
        # greedy longest alias match (up to 4 words) — shared with the editor walker
        m = match_field(self.toks, self.i)
        if m is None:
            # Fallback: a single WORD that is a raw works-registry column_id is
            # always accepted as an input alias (oxjob #363), even with no curated
            # friendly name. Synthesized from the registry; renders back to the
            # raw id. Skipped in ctx_mode so the editor still offers completions.
            t0 = self.peek()
            if not self._ctx_mode and t0 is not None and t0.kind == "WORD":
                raw = _registry_fallback_field(t0.val)
                if raw is not None:
                    self.i += 1
                    return t0.val, raw
            if self._ctx_mode:
                # an unknown / still-being-typed word where a field is expected is
                # the FIELD slot (the editor offers field completions there)
                self._ctx = (CTX_FIELD, {})
                raise _CtxFound()
            t = self.peek()
            raise oql_error("OQL_UNKNOWN_FIELD",
                           f'unknown field "{t.val if t else ""}"',
                           None, t.pos if t else None)
        spelling, fld, n = m
        self.i += n
        return spelling, fld

    def _parse_operator(self) -> str:
        self._skip_annot()
        self._want(CTX_OPERATOR, fld=self._cur_fld)
        t = self.peek()
        if t is None:
            raise oql_error("OQL_MISSING_OPERATOR", "expected an operator")
        # The shared matcher recognizes every COMPLETE operator (incl. the collection
        # `is [not] in collection` forms); for those, consume exactly what it reports.
        m = match_operator(self.toks, self.i)
        # Editor context: an INCOMPLETE multi-word operator (`is any`, `is not`,
        # `is similar`, `does not`) whose tokens run right up to the cursor is
        # "still being typed" — offer operator completion rather than the strict
        # path's degrade-to-`is`. This is the one intentional parser/editor split
        # (see match_operator's docstring); it lives HERE so it can't drift.
        if (self._ctx_mode and m is not None and not m[2]
                and self.i + m[1] >= len(self.toks)):
            self._ctx = (CTX_OPERATOR, {"fld": self._cur_fld})
            raise _CtxFound()
        if m is not None and m[2]:  # complete
            op, n, _complete, _opens = m
            self.i += n
            return op
        # Not a complete operator. Replicate the fail-fast fallbacks: a partial
        # `is …` (e.g. `is any`, `is similar`) degrades to the bare `is` operator
        # (the tail becomes the value); a partial `does …` has no shorter form, so
        # it's a missing-operator error; anything else isn't an operator at all.
        if t.kind == "WORD" and t.val.lower() == "is":
            self.next()
            return "is"
        if t.kind == "WORD" and t.val.lower() in ("does", "doesn't", "doesnt"):
            raise oql_error("OQL_MISSING_OPERATOR", 'expected "does not contain"')
        raise oql_error("OQL_MISSING_OPERATOR",
                       f'expected an operator, got "{t.val}"', None, t.pos)

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
        # the cursor after "it's …" expects a boolean property phrase
        self._want(CTX_VALUE, kind="bool")
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
            raise oql_error("OQL_UNKNOWN_BOOLEAN",
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
                raise oql_error("OQL_BAD_COLLECTION_REF",
                               f'"is in collection" needs a collection id (col_…), got "{v}"',
                               'e.g. work is in collection col_abc123')
            return LeafFilter(fld.column, v, "in collection",
                              is_negated=(op == "nincoll"))
        # the removed value-list openers: `is any of (...)` / `is in (...)` /
        # `is not any of (...)` / `is not in (...)`. Lists are now parens-boolean
        # (`is (a or b)`); give a targeted migration error.
        if op in ("in", "nin"):
            raise oql_error("OQL_LIST_KEYWORD_REMOVED",
                           '"is any of (…)" / "is in (…)" were removed; '
                           "write the list with parentheses",
                           f'e.g. {field} is (a or b)')
        # comparison — always a single bare scalar (D5)
        if op in (">", ">=", "<", "<="):
            v = self._parse_scalar(fld)
            return LeafFilter(fld.column, v, op)
        # is / is not
        negated = (op == "isnot")
        # a parenthesized boolean group of values: `country is (us or uk)`,
        # `country is not (us or uk)` (the base operator negates the whole group)
        t = self.peek()
        if t is not None and t.kind == "LP":
            self.next()
            grp = self._parse_bool_expr(lambda: self._parse_value_operand(fld))
            self._expect_rp()
            return _negate(grp) if negated else grp
        # unknown / null
        if self.word_is("unknown", "null"):
            self.next()
            return LeafFilter(fld.column, None, "is", is_negated=negated)
        # a numeric range value: `year is 2019-2023` / `2019-` / `-2023` -> bound
        # leaves (>= lo AND <= hi). A closed range is an implicit AND that flattens
        # into the top-level filter_rows, so it round-trips to the same OQO the URL
        # parser builds from `publication_year:2019-2023`. (oxjob #363)
        if fld.kind == "num":
            t = self.peek()
            if t is not None and t.kind == "WORD" and "-" in t.val:
                bounds = _parse_num_range(t.val, fld, t.pos)
                if bounds is not None:
                    self.next()
                    self._skip_annot()
                    rng = (bounds[0] if len(bounds) == 1
                           else BranchFilter(join="and", filters=bounds))
                    return _negate(rng) if negated else rng
        # a single bare value; 2+ bare values must be parenthesized (D1)
        v = self._parse_scalar(fld)
        self._skip_annot()
        if self._continues_value():
            t2 = self.peek()
            raise oql_error("OQL_UNDELIMITED_TERM_LIST",
                           f'"{field}" got more than one value with no parentheses',
                           f'wrap the values, e.g. {field} is (a or b)',
                           t2.pos if t2 else None)
        return LeafFilter(fld.column, v, "is", is_negated=negated)

    def _parse_value_operand(self, fld: Field) -> FilterType:
        """One operand inside an `is (...)` value group: a `not`-prefixed operand,
        a nested `(...)` group, or one scalar value (-> an `is` leaf)."""
        t = self.peek()
        if t is not None and t.kind == "WORD" and t.val.lower() == "not":
            self.next()
            return _negate(self._parse_value_operand(fld))
        if t is not None and t.kind == "LP":
            self.next()
            e = self._parse_bool_expr(lambda: self._parse_value_operand(fld))
            self._expect_rp()
            return e
        if t is not None and t.kind == "COMMA":
            raise oql_error("OQL_COMMA_IN_GROUP",
                           "items in a (…) group are separated by 'or'/'and', "
                           "not commas",
                           "replace the comma with 'or' (or 'and')", t.pos)
        v = self._parse_scalar(fld)
        return LeafFilter(fld.column, v, "is")

    def _continues_value(self) -> bool:
        """At the cursor, just after a single bare term/value: does another bare
        operand (or a same-level connective leading to one) follow? If so the user
        wrote an undelimited 2+ list (D1) and must parenthesize it. A connective
        that begins a NEW field clause, a directive, a closing paren / `;` / end
        are all fine (the value is complete)."""
        t = self.peek()
        if t is None or t.kind in ("RP", "SEMI", "COMMA"):
            return False
        if t.kind == "WORD" and t.val.lower() in ("sort", "group", "sample"):
            return False
        if t.kind == "WORD" and t.val.lower() in _CONNECTIVES:
            # `... and year is 2020` (new clause) is fine; `... or bar` is not.
            return not self._looks_like_new_clause(1)
        # an adjacent token that starts a new field clause is handled upstream as
        # implicit adjacency; anything else is a second bare term/value.
        if self._looks_like_new_clause(0):
            return False
        return True

    def _parse_scalar(self, fld: Field):
        # an empty value slot at the cursor (scalar or list element)
        self._want(CTX_VALUE, fld=fld, in_list=self._in_list)
        # An entity ref with only a [display name] annotation and no ID is the
        # classic v1.1 footgun — the ID is authoritative, so require it.
        if fld.kind == "id":
            t0 = self.peek()
            if t0 is not None and t0.kind == "ANNOT":
                raise oql_error("OQL_MISSING_ENTITY_ID",
                               f'"{fld.oql}" needs an ID, not just a [display name]',
                               'put the OpenAlex ID first, e.g. institution is I136199984 [Harvard]',
                               t0.pos)
        self._skip_annot()
        t = self.peek()
        if t is None:
            raise oql_error("OQL_MISSING_VALUE", f'expected a value for "{fld.oql}"', "")
        if t.kind == "STRING":
            self.next()
            val = t.val
        elif t.kind == "WORD":
            self.next()
            val = t.val
        else:
            raise oql_error("OQL_MISSING_VALUE",
                           f'expected a value for "{fld.oql}", got "{t.val}"', "", t.pos)
        self._skip_annot()  # drop a trailing [display name] annotation
        # type coercion per kind
        if fld.kind == "num":
            return _coerce_number(val, fld, t.pos)
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
        self._want(CTX_VALUE, fld=fld, kind="search")
        t = self.peek()
        if t is None or t.kind != "STRING":
            raise oql_error("OQL_SEMANTIC_NEEDS_TEXT",
                           '"is similar to" needs a quoted text passage',
                           'e.g. abstract is similar to "..."', t.pos if t else None)
        self.next()
        return LeafFilter(fld.column + ".search.semantic", t.val, "contains")

    def _parse_search_value(self, base: str) -> FilterType:
        """Top-level value after `contains`: a single bare atom, or a `(...)`
        boolean group. 2+ bare atoms (`title contains foo bar`, `... foo or bar`)
        are a loud OQL_UNDELIMITED_TERM_LIST (D1) — that's the rule that kills the
        silent-keyword-truncation footgun, since a reserved word can only float
        when there are 2+ unparenthesized terms."""
        self._skip_annot()
        self._want(CTX_VALUE, fld=self._cur_fld, kind="search")
        t = self.peek()
        if t is not None and t.kind == "LP":
            self.next()
            e = self._parse_bool_expr(lambda: self._parse_search_operand(base))
            self._expect_rp()
            return e
        if t is not None and t.kind == "WORD" and t.val.lower() == "not":
            raise oql_error("OQL_UNDELIMITED_TERM_LIST",
                           '"not" must be inside a parenthesized term group',
                           f"wrap it in parentheses, e.g. contains (not foo)", t.pos)
        if (t is not None and t.kind == "WORD" and t.val.lower() in ("any", "all")
                and self.word_is("of", k=1)):
            raise oql_error("OQL_LIST_KEYWORD_REMOVED",
                           f'"{t.val.lower()} of (…)" was removed; '
                           "write the list with parentheses",
                           "e.g. contains (a or b)", t.pos)
        leaf = self._parse_search_atom(base)
        self._skip_annot()
        if self._continues_value():
            t2 = self.peek()
            raise oql_error("OQL_UNDELIMITED_TERM_LIST",
                           "two or more search terms with no parentheses "
                           "(a reserved word could be silently swallowed)",
                           'wrap the terms, e.g. contains (a or b), or quote a '
                           'phrase, e.g. contains "a b"', t2.pos if t2 else None)
        return leaf

    def _parse_bool_expr(self, parse_operand) -> FilterType:
        """A boolean group body inside `(...)`: explicit-connective-separated
        *runs* of space-adjacent operands (implicit AND). Mixing a space-run or
        an explicit `and` with an explicit `or` at one level is a loud
        OQL_MIXED_BOOL_NEEDS_PARENS — we never silently pick precedence.
        `parse_operand` reads one operand (search term or value, per the caller).
        Shared by the search side (`contains (...)`) and the value side
        (`is (...)`) so they can't drift."""
        outer = self._in_list
        self._in_list = True
        try:
            unit, n = self._parse_bool_run(parse_operand)
            units = [unit]
            implicit_and = n > 1
            conns: List[str] = []
            while True:
                self._skip_annot()
                t = self.peek()
                if t is None or t.kind in ("RP", "SEMI", "COMMA"):
                    break
                if t.kind == "WORD" and t.val.lower() in _CONNECTIVES:
                    # inside a (...) group every connective is a group connective —
                    # no `_starts_new_clause` check (there are no clauses in a group,
                    # and a value like the language code `it` must not be mistaken
                    # for the `it's …` boolean-phrase clause-start).
                    conns.append(t.val.lower())
                    self.next()
                    unit, n = self._parse_bool_run(parse_operand)
                    units.append(unit)
                    implicit_and = implicit_and or n > 1
                    continue
                break
            effective = set(conns) | ({"and"} if implicit_and else set())
            if "and" in effective and "or" in effective:
                raise oql_error(
                    "OQL_MIXED_BOOL_NEEDS_PARENS",
                    "mixed and/or at one level is ambiguous — add parentheses "
                    "(a space between words is an AND)",
                    'group explicitly, e.g. "a (b or c)" or "(a b) or c"',
                    self.toks[0].pos)
            if not conns:
                return units[0]
            return BranchFilter(join=conns[0], filters=units)
        finally:
            self._in_list = outer

    def _group_operand(self, parse_operand) -> FilterType:
        """Read one group operand. In recover mode (``parse_collecting``) a bad
        operand is recorded and we synchronize to the next group boundary (the
        next connective / ``)`` / ``;`` / end) so every bad item in a group is
        collected, not just the first. Strict mode is a plain ``parse_operand()``."""
        if not self._recover_mode:
            return parse_operand()
        si = self.i
        try:
            return parse_operand()
        except OQLError as e:
            self._diagnostics.append(e)
            self._synchronize()
            if self.i == si:
                t = self.peek()
                if t is not None and t.kind not in ("RP", "SEMI", "COMMA") and not (
                        t.kind == "WORD" and t.val.lower() in _CONNECTIVES):
                    self.next()  # guarantee forward progress
            return self._recovery_placeholder()

    def _parse_bool_run(self, parse_operand) -> Tuple[FilterType, int]:
        """One or more space-adjacent operands = implicit AND. Returns
        (filter, n_operands) so the caller can apply the mixed-and/or rule."""
        atoms = [self._group_operand(parse_operand)]
        while True:
            self._skip_annot()
            t = self.peek()
            if t is None or t.kind in ("RP", "SEMI", "COMMA"):
                break
            if t.kind == "WORD" and t.val.lower() in _CONNECTIVES:
                break  # explicit connective -> handled by _parse_bool_expr
            if t.kind == "WORD" and t.val.lower() in ("sort", "group", "sample"):
                break
            atoms.append(self._group_operand(parse_operand))  # implicit AND
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

    def _looks_like_new_clause(self, k: int) -> bool:
        """Like `_starts_new_clause`, but does NOT require the field to be a known
        alias — any word (or `it's …`) followed within a few tokens by an operator
        looks like a new clause. Used by the arity guard (`_continues_value`) so a
        misspelled/unknown next field (`year is 2020 and bogus is 5`) is treated as
        a new (bad) clause to report, not as a second undelimited value."""
        save = self.i
        self.i += k
        self._skip_annot()
        try:
            t = self.peek()
            # a `(` opens a clause-group; `it's …` opens a boolean clause
            if t and t.kind == "LP":
                return True
            if t and t.kind == "WORD" and t.val.lower() in ("it's", "its", "it"):
                return True
            for j in range(0, 4):
                tt = self.peek(j)
                if not tt or tt.kind != "WORD":
                    break
                after = self.peek(j + 1)
                if after and (after.kind == "OP" or
                              (after.kind == "WORD" and after.val.lower() in
                               ("is", "contains", "does", "doesn't", "doesnt"))):
                    return True
            return False
        finally:
            self.i = save

    def _parse_search_operand(self, base: str) -> FilterType:
        """One operand inside a `contains (...)` group: a `not`-prefixed operand,
        a nested `(...)` group, or one search atom."""
        self._skip_annot()
        # an empty search-term slot at the cursor (`title contains |`)
        self._want(CTX_VALUE, fld=self._cur_fld, kind="search")
        t = self.peek()
        if t is None:
            raise oql_error("OQL_MISSING_VALUE", "expected a search term", "")
        if t.kind == "WORD" and t.val.lower() == "not":
            self.next()
            return _negate(self._parse_search_operand(base))
        if t.kind == "LP":
            self.next()
            e = self._parse_bool_expr(lambda: self._parse_search_operand(base))
            self._expect_rp()
            return e
        if (t.kind == "WORD" and t.val.lower() in ("any", "all")
                and self.word_is("of", k=1)):
            raise oql_error("OQL_LIST_KEYWORD_REMOVED",
                           f'"{t.val.lower()} of (…)" was removed; '
                           "write the list with parentheses",
                           "e.g. contains (a or b)", t.pos)
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
            raise oql_error("OQL_MISSING_VALUE", "expected a search term",
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
                raise oql_error("OQL_BAD_PROXIMITY", 'expected a number after "within"',
                               'e.g. within 3 words', nt.pos if nt else None)
            n = int(nt.val)
            self.next()
            if not self.word_is("words", "word"):
                raise oql_error("OQL_BAD_PROXIMITY", 'expected "words" after the number',
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
                    raise oql_error("OQL_BINARY_PROXIMITY_NEEDS_PHRASES",
                                   'binary proximity needs a quoted phrase after "of"',
                                   'e.g. "smart" within 3 words of "phone"',
                                   bt.pos if bt else None)
                right = bt.val
                self.next()
                # Binary proximity is exact-only (both operands quoted, no-stem). `near`
                # (stemmed) on operand A is not supported here.
                if not phrase or stemmed_phrase:
                    raise oql_error("OQL_BINARY_PROXIMITY_NEEDS_PHRASES",
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
                raise oql_error("OQL_WILDCARD_IN_PROXIMITY",
                               'a wildcard cannot be combined with proximity',
                               'drop the wildcard, or drop "within N words"', t.pos)
            if not phrase or len(text.split()) < 2:
                raise oql_error("OQL_PROXIMITY_NEEDS_PHRASE",
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
                raise oql_error("OQL_WILDCARD_NEEDS_EXACT",
                               f'wildcards run on exact (no-stem) text, but "near" '
                               f'keeps the phrase stemmed: "{text}"',
                               'drop "near" so the wildcard runs on exact text', t.pos)
            raise oql_error("OQL_WILDCARD_NEEDS_EXACT",
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
        self._want(CTX_FIELD, directive="sort")
        t = self.peek()
        if not t or t.kind != "WORD":
            raise oql_error("OQL_BAD_SORT", "expected a field to sort by", "")
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
        self._want(CTX_VALUE, kind="num", field="sample")
        t = self.peek()
        if not t or t.kind != "WORD" or not t.val.isdigit():
            raise oql_error("OQL_BAD_SAMPLE", 'expected a number after "sample"',
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
        raise oql_error("OQL_LEADING_WILDCARD",
                       f'leading wildcard "{word}" is not supported (too expensive)',
                       'anchor the wildcard with leading characters, e.g. cycle*', pos)
    star = word.find("*")
    if star != -1:
        prefix = re.match(r"\w*", word).group(0)
        if star < 3 or len(prefix) < 3 or star > len(prefix):
            # require >=3 word chars immediately before the *
            chars_before = len(re.match(r"\w*", word).group(0)[:star])
            if chars_before < 3:
                raise oql_error("OQL_SHORT_WILDCARD_PREFIX",
                               f'wildcard needs at least 3 leading characters: "{word}"',
                               'add characters before the *, e.g. abc*', pos)
    q = word.find("?")
    if q != -1:
        if q == 0 or not (word[q - 1].isalnum()):
            raise oql_error("OQL_LEADING_WILDCARD",
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
        raise oql_error("OQL_TOO_MANY_WILDCARDS",
                       f'at most {MAX_WILDCARDS_PER_INTERVALS} wildcards are allowed in '
                       f'one phrase or proximity search (this has {len(wild)})',
                       'remove a wildcard, or split into separate searches', pos)
    for w in wild:
        # Only a trailing-`*` prefix drives multiplicative expansion; require a longer
        # anchor for it when a second wildcard is present.
        if w.endswith("*") and w.count("*") == 1 and "?" not in w:
            if len(w) - 1 < MULTI_WILDCARD_MIN_PREFIX:
                raise oql_error("OQL_MULTI_WILDCARD_SHORT_PREFIX",
                               f'with two wildcards in one phrase or proximity search, '
                               f'each * needs at least {MULTI_WILDCARD_MIN_PREFIX} '
                               f'leading characters (for performance): "{w}"',
                               'use a longer prefix (e.g. abcd*) or drop a wildcard', pos)


def parse(oql: str) -> OQO:
    """OQL text -> OQO. Raises OQLError (with .code/.fixit) on any error case."""
    toks = lex(oql)
    if not toks:
        raise oql_error("OQL_EMPTY", "empty query", 'e.g. "works where year >= 2020"')
    p = _Parser(toks)
    oqo = p.parse()
    return oqo


def parse_with_hints(oql: str):
    toks = lex(oql)
    p = _Parser(toks)
    return p.parse(), p.hints


def parse_collecting(oql: str) -> Tuple[Optional[OQO], List[OQLError]]:
    """OQL text -> (OQO_or_None, [OQLError, ...]) collecting EVERY clause-level parse
    error instead of failing on the first (the editor `/validate` path; oxjob #363).

    The strict ``parse()`` above is unchanged — recovery lives entirely behind the
    parser's ``_recover_mode`` flag, branched only at the operand and list-element
    boundaries. A clean parse returns ``(oqo, [])``; an empty input or a lexer error
    (unterminated string/annotation — there are no tokens to recover across) returns
    a single diagnostic, matching ``parse()``'s first-error for those cases."""
    try:
        toks = lex(oql)
    except OQLError as e:
        return None, [e]
    if not toks:
        return None, [oql_error("OQL_EMPTY", "empty query",
                                'e.g. "works where year >= 2020"')]
    return _Parser(toks).parse_collecting()


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


def _value_needs_quote(value: str) -> bool:
    """A bare value atom is one token: it must be quoted if it contains whitespace
    (else `ebook platform` re-parses as the adjacency-AND of two atoms) or collides
    with a grammar keyword / delimiter. (oxjob #363 — first hit by multi-word
    source-type slugs like `ebook platform`, `book series`.)"""
    if not value:
        return False
    return (any(c.isspace() for c in value)
            or value.lower() in _CONNECTIVES
            or value.lower() in ("not", "is", "contains", "where", "sort", "group",
                                 "sample", "unknown", "null")
            or any(c in value for c in "()[],;\""))


def _render_value(fld, value) -> str:
    if value is None:
        return "unknown"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str) and not value.startswith("col_") and _value_needs_quote(value):
        return f'"{value}"'
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


# Max length of a `[display name]` annotation before it's truncated with an
# ellipsis. Uniform across every resolved name (work titles are the worst case,
# but long institution/source names get clipped too). (oxjob #363 case 7)
_NAME_ANNOTATION_MAX = 50


def _truncate_name(name: str) -> str:
    """Clip a display-name annotation to a uniform length with an ellipsis."""
    name = " ".join(name.split())  # collapse internal whitespace/newlines
    if len(name) > _NAME_ANNOTATION_MAX:
        return name[: _NAME_ANNOTATION_MAX - 1].rstrip() + "…"
    return name


def _value_with_name(fld, value, column_id, resolver) -> str:
    """Render a value, appending ` [display name]` when the column resolves names
    and a resolver is supplied (institutions, authors, …, country codes). The name
    is truncated to a uniform length with an ellipsis."""
    rendered = _render_value(fld, value)
    if (resolver and fld and fld.resolves_name and isinstance(value, str)
            and not value.startswith("col_")):
        name = _call_resolver(resolver, value, column_id)
        if name:
            return f"{rendered} [{_truncate_name(name)}]"
    return rendered


def _uniform_search_base(f: FilterType):
    """If every leaf anywhere under `f` is a plain (non-semantic) search leaf on
    the same *base* field, return a representative column_id; else None. The whole
    boolean subtree then factors into one `field contains (...)` clause whose
    parens hold the boolean of bare terms (`title contains (a or (b and c))`).
    Grouping by base field (not full column_id) lets a mixed stemmed/exact group
    — `.search` + `.search.exact` — factor; each leaf keeps its own column so
    `_render_term` renders its mode surface (bare vs quoted)."""
    bases = set()
    rep = [None]

    def walk(node) -> bool:
        if isinstance(node, LeafFilter):
            if not _is_search_leaf(node):
                return False
            name, mode = _oql_field(node.column_id)
            if mode == "semantic":
                return False
            bases.add(name)
            if rep[0] is None:
                rep[0] = node.column_id
            return True
        return all(walk(c) for c in node.filters)

    if not walk(f) or len(bases) != 1:
        return None
    return rep[0]


def _uniform_eq_column(f: FilterType):
    """If every leaf anywhere under `f` is an `is` value leaf (any polarity) on the
    same column, return that column_id; else None. The subtree factors into one
    `field is (...)` clause. Comparisons, null (`is unknown`) and `in collection`
    leaves are excluded — they have no bare-value surface inside the parens."""
    cols = set()

    def walk(node) -> bool:
        if isinstance(node, LeafFilter):
            if not (node.operator == "is" and node.value is not None
                    and not _is_search_leaf(node)):
                return False
            cols.add(node.column_id)
            return True
        return all(walk(c) for c in node.filters)

    if not walk(f) or len(cols) != 1:
        return None
    return cols.pop()


def _factored_segments(f: FilterType, render_leaf):
    """Segments for a factored boolean group's INNER text (no outer parens): a
    boolean of bare atoms with explicit ` or `/` and ` connectives; any child
    sub-group is wrapped in its own parens (the canonicalizer flattens same-join
    nesting, so a child branch always has the opposite join and needs them).
    `render_leaf(leaf) -> [Segment]` renders one bare atom."""
    if isinstance(f, LeafFilter):
        prefix = [_seg("text", "not ")] if f.is_negated else []
        return prefix + render_leaf(f)
    segs = []
    for i, c in enumerate(f.filters):
        if i:
            segs.append(_seg("text", f" {f.join} "))
        inner = _factored_segments(c, render_leaf)
        if isinstance(c, BranchFilter):
            segs = segs + [_seg("text", "(")] + inner + [_seg("text", ")")]
        else:
            segs = segs + inner
    return segs


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
            shown = _truncate_name(name)  # uniform clip — must match _value_with_name
            segs.append(_seg("text", " "))
            segs.append(_seg("id", f"[{shown}]", entity_display_name=shown,
                             entity_display_id=f"[{shown}]"))
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
    # factor a single-base-field search subtree -> `field contains (a or b)`
    scol = _uniform_search_base(f)
    if scol is not None:
        name, _ = _oql_field(scol)
        inner = _factored_segments(
            f, lambda lf: [_seg("value", _render_term(lf.value, lf.column_id),
                                value=lf.value)])
        segs = ([_seg("column", name, column_id=scol),
                 _seg("operator", " contains "), _seg("text", "(")]
                + inner + [_seg("text", ")")])
        return ClauseNode(segments=segs, clause_kind="text", meta=ClauseMeta(
            column_id=scol, operator="contains", value=None,
            column_display_name=name))
    # factor a single-column equality subtree -> `field is (a or b)`
    ecol = _uniform_eq_column(f)
    if ecol is not None:
        fld = _BY_COLUMN.get(ecol)
        name = fld.oql if fld else ecol
        inner = _factored_segments(
            f, lambda lf: _value_segments(fld, lf.value, lf.column_id, resolver)[0])
        segs = ([_seg("column", name, column_id=ecol),
                 _seg("operator", " is "), _seg("text", "(")]
                + inner + [_seg("text", ")")])
        kind = "entity" if (fld and fld.kind == "id") else "other"
        return ClauseNode(segments=segs, clause_kind=kind, meta=ClauseMeta(
            column_id=ecol, operator="is", value=None,
            column_display_name=name))
    children = [_filter_node(c, top=False, resolver=resolver) for c in f.filters]
    joiner = f" {f.join} "
    prefix, suffix = ("", "") if top else ("(", ")")
    return GroupNode(join=f.join, children=children, prefix=prefix, suffix=suffix,
                     joiner=joiner, meta=GroupMeta(implicit=False))


def _fmt_num(v):
    """Render a numeric bound: ints bare (2019), floats verbatim (1.5)."""
    return str(v)


def _range_clause_node(column_id, lo, hi) -> ClauseNode:
    """A merged numeric range clause: `col is lo-hi` / `lo-` / `-hi`."""
    fld = _BY_COLUMN.get(column_id)
    name = fld.oql if fld else column_id
    text = f"{'' if lo is None else _fmt_num(lo)}-{'' if hi is None else _fmt_num(hi)}"
    segs = [_seg("column", name, column_id=column_id),
            _seg("operator", " is "),
            _seg("value", text, value=text)]
    return ClauseNode(segments=segs, clause_kind="comparison", meta=ClauseMeta(
        column_id=column_id, operator="is", value=text, column_display_name=name))


def _merge_num_range_rows(filter_rows):
    """Collapse a same-column inclusive numeric bound PAIR among the (implicit-AND)
    top-level filter_rows into a single closed-range render-item `a-b` (oxjob #363).

    Only a closed range collapses — a column with exactly one `>=a` and one `<=b`
    and no other bound. A SINGLE-ended bound stays an inequality: a lone `>=2020`
    renders `year >= 2020`, not `year is 2020-` (the `2020-` / `-2023` open forms
    are still ACCEPTED on input — see `_parse_num_range` — but are not canonical).
    Strict `>`/`<` (lone, or float pairs the canonicalizer left strict), negated
    bounds, and multi-bound columns are likewise left as inequalities.
    Returns a list whose items are either an original FilterType or a
    ("range", column_id, lo, hi) tuple, in first-occurrence order."""
    def is_bound(f):
        return (isinstance(f, LeafFilter) and not f.is_negated
                and f.operator in (">", ">=", "<", "<=") and f.value is not None
                and (_BY_COLUMN.get(f.column_id) or Field("", "", "")).kind == "num")
    # gather per-column bound indices
    lowers, uppers = {}, {}  # col -> list[(idx, op, value)]
    for i, f in enumerate(filter_rows):
        if not is_bound(f):
            continue
        (lowers if f.operator in (">", ">=") else uppers).setdefault(f.column_id, []).append(
            (i, f.operator, f.value))
    collapse = {}   # first-idx -> ("range", col, lo, hi)
    consumed = set()
    cols = set(lowers) | set(uppers)
    for col in cols:
        los, his = lowers.get(col, []), uppers.get(col, [])
        inc_lo = [b for b in los if b[1] == ">="]
        inc_hi = [b for b in his if b[1] == "<="]
        if len(inc_lo) == 1 and len(inc_hi) == 1 and len(los) == 1 and len(his) == 1:
            anchor = min(inc_lo[0][0], inc_hi[0][0])
            collapse[anchor] = ("range", col, inc_lo[0][2], inc_hi[0][2])
            consumed.update({inc_lo[0][0], inc_hi[0][0]})
    items = []
    for i, f in enumerate(filter_rows):
        if i in collapse:
            items.append(collapse[i])
        elif i in consumed:
            continue
        else:
            items.append(f)
    return items


def _row_node(item, top, resolver):
    if isinstance(item, tuple) and item and item[0] == "range":
        return _range_clause_node(item[1], item[2], item[3])
    return _filter_node(item, top=top, resolver=resolver)


def _build_tree(oqo: OQO, resolver=None) -> OQLRenderTree:
    """OQO -> canonical `oql_render` tree. `render()` stringifies this; the two
    never drift (Invariant A by construction)."""
    head = EntityHead(id=oqo.get_rows, text=oqo.get_rows.lower())
    where_keyword = ""
    where = None
    if oqo.filter_rows:
        where_keyword = " where "
        rows = _merge_num_range_rows(oqo.filter_rows)
        if len(rows) == 1:
            where = _row_node(rows[0], top=True, resolver=resolver)
        else:
            children = [_row_node(f, top=False, resolver=resolver) for f in rows]
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
    """If `clause` is a factored group clause (`… contains (a or b or …)` /
    `… is (a or b or …)`), return `(head, items, conn, close)` where `head` ends
    with `"("`, `items` is the list of top-level item strings, `conn` is the
    group's connective (`"or"`/`"and"`), and `close == ")"`; else None. Splits on
    the engine's own structural segments (the literal `"("`, `" or "`/`" and "`,
    `")"` text segments) at paren-depth 0 only, so a connective inside a nested
    sub-group `(b and c)` is never mistaken for a top-level separator."""
    segs = clause.segments
    open_idx = next((i for i, s in enumerate(segs)
                     if s.kind == "text" and s.text == "("), None)
    if open_idx is None or not (segs[-1].kind == "text" and segs[-1].text == ")"):
        return None
    head = "".join(s.text for s in segs[:open_idx + 1])
    items, cur, conn, depth = [], [], None, 0
    for s in segs[open_idx + 1:-1]:
        if s.kind == "text" and s.text == "(":
            depth += 1
            cur.append(s.text)
        elif s.kind == "text" and s.text == ")":
            depth -= 1
            cur.append(s.text)
        elif depth == 0 and s.kind == "text" and s.text in (" or ", " and "):
            items.append("".join(cur))
            cur = []
            conn = s.text.strip()
        else:
            cur.append(s.text)
    items.append("".join(cur))
    if conn is None or len(items) < 2:
        return None  # a single bare atom / unbreakable clause
    return head, items, conn, ")"


def _fmt_list(head: str, items, conn: str, indent: int, width: int) -> str:
    """Lay out an exploded factored group. `indent` is the clause's own indent
    (where the closing `)` sits); items sit at `indent + _INDENT`. The connective
    trails every item but the last (idempotence anchor + clean diffs; the parser
    is whitespace-blind). <=8 items -> one per line; >8 -> fill/pack to `width`."""
    pad = " " * (indent + _INDENT)
    out = [head]
    n = len(items)

    def piece(i, it):
        return it if i == n - 1 else f"{it} {conn}"

    if n <= 8:
        out.extend(f"{pad}{piece(i, it)}" for i, it in enumerate(items))
    else:
        line, empty = pad, True
        for i, it in enumerate(items):
            p = piece(i, it)
            if not empty and len(line) + 1 + len(p) > width:
                out.append(line)
                line, empty = pad, True
            line = f"{pad}{p}" if empty else f"{line} {p}"
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
    head, items, conn, _close = parts
    return _fmt_list(head, items, conn, indent, width)


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
    lines = []
    if tree.where is not None:
        # Keep the entity head on the same line as `where` (and the first
        # clause): `works where institution is …`, with continuation operands
        # wrapping below at `_INDENT`. The prefix's width seeds the column so the
        # first clause still wraps correctly when it alone overflows.
        prefix = f"{tree.entity.text}{tree.where_keyword}"   # e.g. "works where "
        body = _fmt_expr(tree.where, _INDENT, len(prefix), width)
        lines.append(f"{prefix}{body}")
    else:
        lines.append(tree.entity.text)
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
