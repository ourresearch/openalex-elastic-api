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
  search terms / values (`title has (a or b)`, `country is (us or uk)`). A
  list of 2+ bare terms/values must be parenthesized; a single one may be bare.
- Only `"` delimits strings; there are no escape sequences.
- Quotes = phrase with stemming ON; `exactly` = non-stemmed; `within N words` =
  whole-phrase proximity; `is similar to` = semantic. Wildcards `* ?` fire only
  bare; in quotes / leading / sub-3-char-prefix / in-proximity are errors.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, replace
from typing import Dict, List, Optional, Tuple

# Load the OQO data model without triggering the Flask-heavy package __init__.
from query_translation.oqo import (  # noqa: E402
    OQO, LeafFilter, BranchFilter, FilterType, GroupBy, CURLY_DQUOTE_MAP,
    canonicalize_oqo_column_ids, normalize_corpus, CORPUS_CANONICAL_PHRASE)


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
# Whether the renderer synthesizes a `[display name]` for a column's values
# (opaque IDs + country codes — human-readable slugs like article/gold don't;
# `article [article]` is noise) is NOT stored here: it derives from the
# registry's `entity_type` via `namespace_for_column` (oxjob #565).
@dataclass
class Field:
    column: str          # base column (search) or full column_id (non-search)
    kind: str
    oql: str             # canonical OQL spelling for rendering
    casing: str = ""     # '' | 'lower' | 'upper'
    is_float: bool = False  # num kind: True = decimals allowed (fwci); False = integer
                            # (year, count). Integer fields collapse a strict bound
                            # PAIR to an inclusive range via ±1 (`>42 and <100` -> 43-99).
    # date kind (oxjob #407). A date AXIS field (publication_date / created_date /
    # updated_date) routes its OPERATOR to one of three real ES `DateField` params:
    #   `is YYYY-MM-DD` -> the base column   (exact day; ES term)
    #   `>= d`          -> date_from_col      (inclusive lower; ES gte)
    #   `<= d`          -> date_to_col        (inclusive upper; ES lte)
    #   strict `>`/`<`  -> the base column   (ES gt/lt)
    # The inclusive bounds MUST go to from_*/to_* — the base param has no gte/lte
    # form at ES (see EXPLORE.md). A date BOUND column (from_*/to_*) carries
    # date_axis (the axis render word, e.g. "date") + date_bound (">="/"<="); it has
    # no standalone render word and renders as `<date_axis> >=|<= <value>`.
    date_from_col: str = ""  # axis field: column for the inclusive lower bound (>=)
    date_to_col: str = ""    # axis field: column for the inclusive upper bound (<=)
    date_axis: str = ""      # bound column: axis word to render with
    date_bound: str = ""     # bound column: ">=" or "<="


_FIELDS: List[Tuple[List[str], Field]] = []  # (alias-spellings, Field)


def _f(oql, column, kind, aliases=(),
       casing=None, is_float=False,
       date_from_col="", date_to_col="", date_axis="", date_bound=""):
    if casing is None:
        casing = "lower" if kind == "enum" else ""
    fld = Field(column=column, kind=kind, oql=oql, casing=casing,
                is_float=is_float, date_from_col=date_from_col, date_to_col=date_to_col,
                date_axis=date_axis, date_bound=date_bound)
    spellings = [oql] + list(aliases)
    _FIELDS.append(([s.lower() for s in spellings], fld))
    return fld


def _canon_value_case(value, fld: "Field"):
    """Apply the column's cosmetic value casing (never touches col_… refs)."""
    if not isinstance(value, str) or value.startswith("col_") or not fld.casing:
        return value
    return value.lower() if fld.casing == "lower" else value.upper()


# ===========================================================================
# ⚠️  GUARDRAIL (oxjob #406) — `_FIELDS` is NOT the place for names or aliases.
#
# The properties registry (`core/properties.py` ENTITY_PROPERTIES, with labels +
# input spellings curated in `core/display_names.py`) is the SOURCE OF TRUTH for
# what a field is *called* (its `display_name`) and what alternate spellings parse
# into it (its `aliases`). That registry is consumed OUTSIDE OQL (the GUI, the
# `/properties` catalog, docs), which is exactly why it's the right place to fix.
#
# `_FIELDS` exists ONLY for OQL's parse/render *mechanics* that the engine registry
# doesn't model: the `kind` (search/id/enum/num/string/bool), value `casing`,
# and the `.search` mode encoding. (Booleans render as a plain
# `<name> is true|false` clause — no sentence templates.) The *column a word resolves
# to per entity* is derived
# from the registry at parse time (`_entity_resolve_field`) and render time
# (`_augment_by_column_for_homonyms`) — NOT hand-mapped here.
#
# So before adding a `_f(...)`: if you're reaching for it to give a field a nicer
# NAME, or to add an input ALIAS, or to surface a field on a NON-works entity —
# STOP. That's a `core/display_names.py` change (it improves the shared registry
# for everyone, not just OQL). Adding it here instead silently forks the source of
# truth and re-introduces the entity-blindness #406 removed. `_FIELDS` is a
# tempting low-effort shortcut; resist it.
# ===========================================================================

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
# oxjob #430: "text" is the non-works broad-search canonical (column `text.search` —
# name + alternate names + description/keywords per entity). Mechanics only here
# (the #406 guardrail); human input aliases ("anywhere"/"any field"/"default") live
# on the registry side in core/display_names.py. `text.search` exists only on
# non-works entities, so the entity-aware resolver maps "text" to it there; "full
# text" stays the works broad word (fulltext.search). Both render their own word —
# no homonym collision, since they are distinct columns.
_f("text", "text", "search", aliases=["text.search"])
_f("raw affiliation", "raw_affiliation_strings", "search",
   aliases=["raw_affiliation_strings.search", "affiliation", "raw affiliation string"])
_f("byline", "raw_author_name", "search",
   aliases=["raw_author_name.search", "raw author name"])
_f("institution name", "institutions.display_name", "search",
   aliases=["institutions.display_name.search"])
# NOTE: OQL deliberately does NOT support keyword free-text search (`keyword.search`).
# The GUI has no keyword text-search facet — its "keyword" is purely the `keywords.id`
# ENTITY picker — so for GUI parity the word "keyword" is the entity filter (registered in
# the ids section below), not a search. (Jason 2026-06-09, #402.) The `keyword.search`
# engine param still exists for raw URLs; OQL just doesn't surface it.

# --- numeric ---
_f("year", "publication_year", "num")
# Render word "citation count" = the registry display_name (#381 v1.5.0): the COUNT,
# kept distinct from the cited_by/cites relationship filters. Old "citations" → alias.
# Friendly input aliases ("citations", "cited by count") live in the properties
# registry (core/display_names.py), not here — the registry-alias fallback parses
# them; _FIELDS keeps only the canonical word + the raw column-id alias. (#406 1c)
_f("citation count", "cited_by_count", "num")
_f("FWCI", "fwci", "num", aliases=["fwci"], is_float=True)
# The work's citation count normalized by subfield + year, as a percentile (0-100).
# Render word = registry display_name "citation percentile by subfield" (#363 case 4).
_f("citation percentile by subfield", "citation_normalized_percentile.value", "num",
   is_float=True)

# --- dates (oxjob #407) ---
# ONE friendly axis field per date; the OPERATOR routes to one of three real ES
# `DateField` params. Render words are the registry display_names ("date" /
# "created date" / "updated date") so the consistency gate stays green with no
# /properties change. Literals are full ISO `YYYY-MM-DD` only (Jason 2026-06-09;
# bare years live at `year is 2020`). Inclusive bounds (`>=`/`<=`) route to the
# from_*/to_* params (the base column has only exact-day + strict >/< at ES — see
# EXPLORE.md). The bound columns are registered too (drops them off the #363 raw
# fallback) and render via the axis word: `date >= 2020-01-01`.
#
# Plan-gating: the created/updated axes are Premium/Institutional/Partner only
# (free keys get HTTP 200 {"error":"Plan upgrade required"}); the engine enforces
# this at query time — OQL just surfaces the fields. Never put a free-tier
# created/updated example in user-facing links; `date` (publication) is free.
_f("date", "publication_date", "date",
   date_from_col="from_publication_date", date_to_col="to_publication_date")
_f("created date", "created_date", "date",
   date_from_col="from_created_date", date_to_col="to_created_date")
_f("updated date", "updated_date", "date",
   date_from_col="from_updated_date", date_to_col="to_updated_date")
# Bound columns: parse the raw from_*/to_* key (so it leaves the #363 fallback and
# a GUI-shared `from_created_date=…` URL round-trips), RENDER via the axis word.
_f("from_publication_date", "from_publication_date", "date", date_axis="date", date_bound=">=")
_f("to_publication_date", "to_publication_date", "date", date_axis="date", date_bound="<=")
_f("from_created_date", "from_created_date", "date", date_axis="created date", date_bound=">=")
_f("to_created_date", "to_created_date", "date", date_axis="created date", date_bound="<=")
_f("from_updated_date", "from_updated_date", "date", date_axis="updated date", date_bound=">=")
_f("to_updated_date", "to_updated_date", "date", date_axis="updated date", date_bound="<=")

# --- booleans (oxjob #363) ---
# Booleans are ordinary subject-predicate-value clauses: `<name> is true|false`
# (the old "it's …"/"it has …" special case was removed). The render word is the
# Field.oql below AND the registry display_name (core/display_names.py) — kept in
# lockstep so OQL, /properties, and the GUI builder all show the same noun.
_f("open access", "open_access.is_oa", "bool")
_f("global south", "institutions.is_global_south", "bool")
_f("retracted", "is_retracted", "bool")
_f("has DOI", "has_doi", "bool")
_f("has ORCID", "has_orcid", "bool")
# Full text available in some open repository (engine open_access.any_repository_has_fulltext).
_f("has repository fulltext", "open_access.any_repository_has_fulltext", "bool")
# Citation-percentile band flags (subfield+year normalized). (#363 case 4 siblings)
_f("top 1% cited", "citation_normalized_percentile.is_in_top_1_percent", "bool")
_f("top 10% cited", "citation_normalized_percentile.is_in_top_10_percent", "bool")

# --- ids (entity references) ---
_f("institution", "authorships.institutions.lineage", "id")
_f("author", "authorships.author.id", "id")
_f("source", "primary_location.source.id", "id")
_f("topic", "primary_topic.id", "id")
_f("topics", "topics.id", "id")
_f("funder", "funders.id", "id")
# Publisher of the work's primary source (engine param primary_location.source.publisher_lineage,
# a P-id; lineage so a parent publisher matches its imprints). Mirrors `funder`: an entity-id
# reference, name-resolved via the publishers namespace. (oxjob #363 discovery loop run #1)
_f("publisher", "primary_location.source.publisher_lineage", "id")
# Render word "SDG" = the registry display_name (#381 Phase 5: acronym made canonical
# everywhere). Long forms stay parse aliases.
# "sustainable development goal(s)" input aliases live in the registry (#406 1c).
_f("SDG", "sustainable_development_goals.id", "id",
   aliases=["sdg"])
_f("last known institution", "last_known_institutions.id", "id")
# `primary_topic.domain.id` is the canonical works column the GUI facets as "domain"
# (entityToSelect domains); `domain.id` is the OQL-only shorthand. Fold the GUI param in
# as an alias so it parses to / renders "domain" and drops off the #363 fallback. (#402)
_f("domain", "domain.id", "id")
_f("field", "primary_topic.field.id", "id")
# subfield of the work's primary topic (topic hierarchy: domain > field > subfield > topic).
# Was missing while its siblings field/domain/topic were registered (oxjob #363 discovery run #2);
# render word = registry display_name "subfield"; name-resolved via the native subfields namespace.
_f("subfield", "primary_topic.subfield.id", "id")
_f("openalex id", "ids.openalex", "id")
# Citation relationships to a specific work (W-id; resolves the work's title).
# cited_by:W = works in W's reference list; referenced_works:W (input alias
# cites:W) = works citing W. Since #557 the FILTER leaves render as row-subject
# verb phrases (`it cites (…)` / `it's cited by (…)` — see _ROW_SUBJECT_RENDER);
# these words surface only on column/sort. The outgoing edge's word is "cites"
# everywhere (word unification, #557) — its row is registered with the other
# work-relationship ids below; the old alias `_f("cites","cites")` row is gone
# (the input word "cites" is now the canonical word itself).
_f("cited by", "cited_by", "id")

# --- collection (same-type membership) ---
# The same-type `collection:` filter: "this row's entity is a member of Collection
# col_…". Surfaced as `<subject> is in collection col_…` where the subject is the
# queried entity (works-centric registry → "work"). Cross-type membership reuses the
# referenced entity's own column (e.g. `country`/`institution`/`author`) — no separate
# field. kind "collection" parses a bare col_… scalar (no name resolution). (oxjob #363)
_f("work", "collection", "collection", aliases=["works"])

# --- enums (slug values) ---
_f("type", "type", "enum")
# Render word "open access status" = the registry display_name (#381 Phase 5); the
# greedy field matcher prefers it over the 2-word "open access" bool when "status"
# follows. Old "OA status" → parse alias.
# "OA status" input alias lives in the registry (#406 1c).
_f("open access status", "open_access.oa_status", "enum", aliases=["oa_status"])
# Country codes: ISO uppercase canonical + resolve a [display name] (Germany, not de).
_f("country", "authorships.countries", "enum", casing="upper")
_f("country code", "country_code", "enum", casing="upper")
_f("author country", "last_known_institutions.country_code", "enum", casing="upper")
# Languages resolve a [display name] (English, not en) from config/languages.yaml,
# like countries — a closed code vocabulary, not a "super obvious" enum. (oxjob #363 case 5)
_f("language", "language", "enum")
# The source's type (journal / conference / repository / ebook platform / book series /
# metadata / other). Render word = the engine registry display_name `source type`
# (`core/display_names.py`). Slug enum; multi-word values like "ebook platform" are
# valid atoms. Distinct from `type` (the WORK's type, column `type`). (oxjob #363)
_f("source type", "primary_location.source.type", "enum")

# --- literal strings ---
_f("DOI", "doi", "string", aliases=["doi"])
# "author orcid" input alias lives in the registry (#406 1c).
_f("ORCID", "authorships.author.orcid", "string")
# The work's journal, by ISSN (engine param primary_location.source.issn; accepts ISSN-L or
# any of a source's ISSNs). Literal string like DOI/ORCID — no name resolution. WoS `IS=`,
# Scopus `ISSN()`. (oxjob #363 discovery loop run #1)
_f("ISSN", "primary_location.source.issn", "string",
   aliases=["issn"])

# --- oxjob #402 friendly-name audit (long-tail GUI/docs columns) ---
# Front-B-only batch: every render word below already equals the column's registry
# `display_name` (no core/display_names.py change, no PROPERTIES_VERSION bump). The
# raw column_id stays a structural alias so the #363 input-alias fallback drops it.

# distinct-count metrics (kind num; registry display_names already clean).
_f("reference count", "referenced_works_count", "num")
_f("institutions count", "institutions_distinct_count", "num")
_f("countries count", "countries_distinct_count", "num")

# DOI prefix match (engine param doi_starts_with; literal string, no resolution).
_f("DOI prefix", "doi_starts_with", "string")

# Corresponding-author / -institution entity-id filters (name-resolved via the
# authors / institutions namespaces, like `author` / `institution`).
_f("corresponding author", "corresponding_author_ids", "id")
_f("corresponding institution", "corresponding_institution_ids", "id")

# Bibliographic coordinates (kind string — volumes/issues/pages are free-text
# labels, e.g. "42", "S1", "iv"). PROPERTIES_VERSION 1.9.0 curated the registry
# display_names from the raw "biblio volume"/… humanized ids.
_f("volume", "biblio.volume", "string")
_f("issue", "biblio.issue", "string")
_f("first page", "biblio.first_page", "string")
_f("last page", "biblio.last_page", "string")

# Legacy / external work ids (kind string — literal, no name resolution).
# Registry display_names curated in 1.9.0 from raw "ids mag"/"ids pmid"/"ids pmcid".
_f("MAG ID", "ids.mag", "string")
_f("PMID", "ids.pmid", "string")
_f("PMCID", "ids.pmcid", "string")

# APC (article processing charge). Only the USD estimated-paid column is curated —
# its registry display_name is already clean ("estimated APC paid", and it's the one
# faceted in the GUI), so this is Front-B only (no display_name change, no version
# bump). It's a currency amount (USD, may be fractional) → num/is_float. The other 7
# apc columns (apc_list.{value,value_usd,currency,provenance}, apc_paid.{value,
# currency,provenance}) are deliberately LEFT OUT OF SCOPE per Jason (2026-06-08):
# native-currency duplicates + provenance/currency metadata aren't worth an OQL
# surface; they stay on the #363 raw-key input-alias fallback as documented residue.
_f("estimated APC paid", "apc_paid.value_usd", "num", is_float=True)

# More Front-B-only columns (registry display_names already clean — no
# core/display_names.py change, no PROPERTIES_VERSION bump).
# ROR id of an affiliated institution (literal string, no name resolution — the
# ROR *is* the identifier the user types). Engine param authorships.institutions.ror.
_f("ROR ID", "authorships.institutions.ror", "string")
# Work-relationship id filters, mirroring cited_by: each references a WORK, so
# they name-resolve via the `works` namespace (edge overrides in namespace_for_column).
# referenced_works = this work's reference list; related_to = OpenAlex "related works".
# #557 word unification: referenced_works's word is "cites" everywhere (filter
# verb, column header, sort) — matching the prod GUI chips and the oxurl input
# alias `cites:`. "references" survives as an accepted input alias (registry
# aliases in core/display_names.py); `reference count` (referenced_works_count)
# keeps its own word. (Declaration order is NOT load-bearing: since #567 the
# reverse-map build asserts loudly if two rows ever claim one column.)
_f("cites", "referenced_works", "id")
_f("related to", "related_to", "id")
# "raw-but-good" distinct-count metrics (kind num, integer counts; display_names
# are auto-humanized but already read cleanly, so Front-B with the existing word).
_f("authors count", "authors_count", "num")
_f("locations count", "locations_count", "num")

# --- oxjob #402 booleans (content / identifier / index flags) ---
# Plain subject-predicate-value bools: `<name> is true|false` (oxjob #363). The
# render word (Field.oql) matches the registry display_name (core/display_names.py);
# input aliases live there too, per the _FIELDS guardrail above.
_f("has abstract", "has_abstract", "bool")
_f("has references", "has_references", "bool")
_f("PubMed", "has_pmid", "bool")
_f("has PMCID", "has_pmcid", "bool")
_f("MAG-only", "mag_only", "bool")
_f("extended index", "is_xpac", "bool")
_f("paratext", "is_paratext", "bool")

# --- oxjob #402 Tier-1 open-access first-class columns ---
_f("best open version", "best_open_version", "string")
_f("indexed in", "indexed_in", "string")
_f("PDF-linked", "has_content.pdf", "bool")
_f("OA accepted", "best_oa_location.is_accepted", "bool")
_f("OA published", "best_oa_location.is_published", "bool")
# "full text" alone is the broad full-text SEARCH field; the availability flag keeps
# the "has …" qualifier to avoid the _ALIAS collision (oxjob #363, Jason's call).
_f("has full text", "has_fulltext", "bool")

# --- oxjob #402 Tier-2 location/source mirror BOOLEANS ---
# Scope words: primary_location unmarked ("primary …"), best_oa_location "best OA …",
# locations "any location …". Names match the registry display_name.
_f("primary OA", "primary_location.is_oa", "bool")
_f("primary published", "primary_location.is_published", "bool")
_f("primary accepted", "primary_location.is_accepted", "bool")
_f("has ISSN", "primary_location.source.has_issn", "bool")
_f("CWTS core", "primary_location.source.is_core", "bool")
_f("DOAJ", "primary_location.source.is_in_doaj", "bool")
_f("OA source", "primary_location.source.is_oa", "bool")
_f("best OA source DOAJ", "best_oa_location.source.is_in_doaj", "bool")
# --- non-works entity booleans (oxjob #406 1c) ---
# `is_oa`/`is_in_doaj` are sources columns. "fully OA" (`is_oa`) also filters
# works.is_oa. The "DOAJ" word is shared with works' primary_location.source.is_in_doaj
# but on a DIFFERENT column — the entity resolver re-points it per entity (the
# `_ALIAS["doaj"]` key is order-dependent but every query is entity-scoped). `is_core`
# ("CWTS core") is a HOMONYM of works' primary_location.source.is_core — no entry
# needed; the resolver maps the word to bare is_core on sources.
_f("fully OA", "is_oa", "bool")
_f("DOAJ", "is_in_doaj", "bool")
_f("any location OA", "locations.is_oa", "bool")
_f("any location published", "locations.is_published", "bool")
_f("any location accepted", "locations.is_accepted", "bool")
_f("any location CWTS core", "locations.source.is_core", "bool")
_f("any location DOAJ", "locations.source.is_in_doaj", "bool")
_f("submitted version OA", "has_oa_submitted_version", "bool")

# --- oxjob #402 Tier-2 location/source mirror STRING / ENUM / ID cols ---
# The mirror set's non-boolean half. These had raw auto-humanized display_names, so this is a
# Front-A batch: core/display_names.py curated to the matrix scope words + PROPERTIES_VERSION
# 1.9.0 -> 1.10.0 (MINOR, blanket-approved), THEN registered here (render word == new
# display_name, enforced by the registry-consistency gate). Scope words mirror the bool block:
# primary unmarked / "best OA …" / "any location …". `primary_location.license` now owns bare
# "license" (resolving the live best_oa/locations duplicate). The host_organization /
# publisher_lineage / host_institution_lineage family is deliberately deferred — its
# publisher-vs-institution-vs-ambiguous-host-org disambiguation is a judgment call grouped
# with batch 7. id cols name-resolve via the `sources` namespace (oql_renderer).
# ISSN / version / license: literal strings (no name resolution), like primary's ISSN.
_f("best OA license", "best_oa_location.license", "string")
_f("any location license", "locations.license", "string")
_f("license", "primary_location.license", "string")
_f("best OA source ISSN", "best_oa_location.source.issn", "string")
_f("any location source ISSN", "locations.source.issn", "string")
_f("primary version", "primary_location.version", "string")
_f("any location version", "locations.version", "string")
# source type: slug enum (mirrors primary's "source type").
_f("best OA source type", "best_oa_location.source.type", "enum")
_f("any location source type", "locations.source.type", "enum")
# source id: entity-id reference, name-resolved via the sources namespace (mirrors primary's
# "source"). Name resolution derives from registry entity_type (#565).
_f("best OA source", "best_oa_location.source.id", "id")
_f("any location source", "locations.source.id", "id")

# --- oxjob #402 batch 7 (GUI-faceted long-tail; scoped to what the current GUI supports
# per Jason 2026-06-09 — anything not GUI-faceted or with ambiguous naming is left out of OQL
# and stays on the #363 raw fallback). All Front-B (registry display_names already clean).
# institution type: the affiliated institution's type (education / healthcare / company / …);
# slug enum, mirrors source type. GUI displayName "institution type".
_f("institution type", "authorships.institutions.type", "enum")
# awards: grant/award entity-id, name-resolved via the awards namespace. GUI displayName
# "awards" (entityToSelect awards). Name resolution derives from entity_type (#565).
_f("awards", "awards.id", "id")
# continent of an affiliated institution. GUI facet "Continent" (entityToSelect continents);
# values are `continents/Q15`-style ids that resolve to a name (Africa, Europe, …) via the
# continents namespace — id kind, like `domain`. (#402 batch 7, Jason-approved 2026-06-09)
_f("continent", "authorships.institutions.continent", "id")
# keyword: the curated-keyword ENTITY filter (GUI facet "keyword", entityToSelect keywords),
# name-resolved via the keywords namespace — like topic/domain. This claims the word "keyword"
# (OQL no longer registers keyword.search; see the search section). Registry display_name for
# keywords.id is already "keyword" → Front-B. (Jason 2026-06-09, #402)
_f("keyword", "keywords.id", "id")

# Reverse map: column_id (final, incl. search suffix stripped to base) -> Field.
# Populated by `_build_by_column()` — the SINGLE build site, defined below once
# its helpers (`_entity_resolve_field`, `_entity_fallback`) exist (oxjob #567).
# Nothing reads this map at import time before that build runs.
_BY_COLUMN: Dict[str, "Field"] = {}


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


def is_numeric_column(column_id) -> bool:
    """True for any num-kind column (integer or float). The type authority for
    the OQO canonicalizer's string→number value coercion."""
    fld = _BY_COLUMN.get(column_id)
    return bool(fld and fld.kind == "num")


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

# `&` is an accepted INPUT synonym for `and` (oxjob #363). It lexes as its own
# WORD token when surrounded by spaces (`&` is not a _WORD_BREAK char, so a spaced
# `&` runs to the next break = a lone "&"); recognizing it here makes every
# connective check (`.val.lower() in _CONNECTIVES`) treat it as `and`. The captured
# token never reaches render — `_precedence_tree` folds any non-`or` connective into
# a `BranchFilter(join="and")`, so canonical output is always the spelled-out `and`.
_CONNECTIVES = {"and", "or", "&"}

# Words that TERMINATE a multi-word search run (#1, oxjob #363) — a connective,
# `not`, or a search/directive keyword the grammar reads after the run. When one
# of these appears as a LITERAL word inside a stemmed search value it must be
# quoted on render (`… "and" …`) so it folds back as an escaped literal rather
# than re-parsing as structure. `_Parser._is_run_break_word` reads this set.
_SEARCH_RUN_RESERVED = _CONNECTIVES | {"not", "stemmed", "within", "group",
                                       "sample"}

# Characters dropped from a STEMMED search value on render (#3, oxjob #363): the
# ES stemmed-search analyzer strips this punctuation anyway (so dropping it is
# result-preserving), and left in place it would break a re-parse — `?`/`*` read
# as bare wildcards (OQL_WILDCARD_NEEDS_EXACT), `|`/`()[]` etc. as structure.
# Genuine wildcards live on the `.search.exact` column and are NOT routed here.
_STEMMED_DROP_CHARS_RE = re.compile(r'[?*|()\[\],;"]')


def _render_stemmed_search_value(value: str) -> str:
    """Render the inner form of a stemmed `.search` value for OQL (#1 single
    node): drop characters that wouldn't survive a stemmed re-parse (#3) and
    quote any embedded reserved word so it reads as a literal, not a connective
    (#2). Returns the space-joined token form WITHOUT the outer parentheses."""
    cleaned = _STEMMED_DROP_CHARS_RE.sub(" ", value or "")
    toks = cleaned.split()
    return " ".join(f'"{t}"' if t.lower() in _SEARCH_RUN_RESERVED else t
                    for t in toks)


# ---------------------------------------------------------------------------
# Lexer
# ---------------------------------------------------------------------------
@dataclass
class Tok:
    kind: str   # WORD | STRING | ANNOT | LP | RP | COMMA | OP | SEMI
    val: str
    pos: int


_WORD_BREAK = set(' \t\n"[](),;!')


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
        if c == '!':
            # within-`.search`-value WoS NOT operator: `A!B` = A AND NOT B (#432).
            # Only meaningful infix inside a `has` value group; the parser
            # (_parse_search_operand) consumes it. A literal `!` must be quoted.
            toks.append(Tok("BANG", c, i)); i += 1; continue
        # WORD: run until a break char
        j = i
        while j < n and s[j] not in _WORD_BREAK:
            j += 1
        toks.append(Tok("WORD", s[i:j], i))
        i = j
    return toks


# ---------------------------------------------------------------------------
# Numeric values (oxjob #363). A num field's value is a single number. The dash
# range literal (`year is 2019-2023`, open-ended `2019-` / `-2023`) was REMOVED as
# OQL surface syntax — charter decision 24: write explicit endpoint clauses
# `year >= 2019 and year <= 2023`. `_RANGE_RE` is kept only to RECOGNIZE a typed
# dash so we can reject it with a targeted fix-it (not a generic "not a number").
# The OpenAlex URL range form `publication_year:2019-2023` and OQO bound leaves are
# unaffected — only the OQL literal goes away; a URL range still renders endpoints.
_RANGE_RE = re.compile(r"^(?P<lo>\d+(?:\.\d+)?)?-(?P<hi>\d+(?:\.\d+)?)?$")


# Full ISO date literal `YYYY-MM-DD` (oxjob #407). Tokenizes as a single WORD ('-'
# and digits are not word-break chars), exactly like the num value `2019-2023`.
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _coerce_date(val: str, fld: "Field", pos):
    """Validate a full-ISO date literal for a date field; returns the string
    verbatim (dates aren't entities or numbers). Bare `2020` / `2020-03` are
    rejected (Jason 2026-06-09 — full ISO only; bare years live at `year`)."""
    if not _DATE_RE.match(val):
        raise oql_error("OQL_BAD_DATE",
                       f'"{val}" is not a date (YYYY-MM-DD) for "{fld.oql}"',
                       "e.g. date is (2020-05-17)", pos)
    return val


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


def _range_endpoints(val: str):
    """If `val` is a removed dash range literal (`2019-2023`, open-ended `2019-` /
    `-2023`), return its `(lo, hi)` numeric sides (either may be None) — charter
    decision 24. Else None. A bare `-`, or a dash term with a non-numeric side
    (`2019-abc`), is NOT a range literal: those fall through to the scalar path and
    surface as OQL_BAD_NUMBER ("not a number"), the accurate diagnosis. Used only to
    raise OQL_RANGE_LITERAL_REMOVED on a typed dash with an endpoint-form fix-it."""
    m = _RANGE_RE.match(val)
    if not m or (m.group("lo") is None and m.group("hi") is None):
        return None
    return m.group("lo"), m.group("hi")


def _range_endpoint_fixit(field: str, lo, hi) -> str:
    """The endpoint-clause rewrite suggested for a rejected dash range literal:
    `field >= lo and field <= hi`, or the single inequality for an open-ended form."""
    parts = []
    if lo is not None:
        parts.append(f"{field} >= {lo}")
    if hi is not None:
        parts.append(f"{field} <= {hi}")
    return " and ".join(parts)


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


def _registry_kind(prop, *, surface_rich_kinds: bool) -> Optional[str]:
    """THE kind-derivation rule for registry-synthesized Fields (oxjob #567) —
    the single function both fallback doors call. (Curated `_f(...)` rows carry
    an explicit hand-picked kind and never come through here.)

    surface_rich_kinds=False is the works raw-column_id door's deliberately
    conservative policy, frozen as-is: a raw column_id renders raw and never
    name-resolves, so it only distinguishes comparable numbers ('range' in
    operators) from verbatim strings — never id/enum/bool.

    surface_rich_kinds=True is the entity-fallback door: `id` for entity
    references (carries `entity_type`), None for booleans (an uncurated bool
    has no render phrasing, so the caller must skip it), `num` for
    numbers/ranges, else verbatim `string`.
    """
    ops = set(getattr(prop, "operators", []) or [])
    if not surface_rich_kinds:
        return "num" if "range" in ops else "string"
    ptype = getattr(prop, "type", None)
    if ptype == "boolean":
        return None
    if getattr(prop, "entity_type", None):
        return "id"
    if ptype == "number" or "range" in ops:
        return "num"
    return "string"


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
        kind = _registry_kind(prop, surface_rich_kinds=False)
        out[key] = Field(column=cid, kind=kind, oql=cid, casing="",
                         is_float=(kind == "num"))
    return out


def _registry_fallback_field(word: str) -> Optional["Field"]:
    """The synthetic Field for a raw registry column_id (case-insensitive), or
    None if `word` isn't a known works column (or the registry is unavailable)."""
    global _REGISTRY_FALLBACK_CACHE
    if _REGISTRY_FALLBACK_CACHE is None:
        _REGISTRY_FALLBACK_CACHE = _build_registry_fallback()
    return _REGISTRY_FALLBACK_CACHE.get(word.lower())


# --- entity-aware word -> column resolution (oxjob #406) -------------------
# OQL's `_FIELDS` registry maps a friendly word to ONE, works-default column, but
# the same word names a DIFFERENT column on a different entity: `domain` is
# `primary_topic.domain.id` on works but bare `domain.id` on topics; `ORCID` is
# `authorships.author.orcid` on works but `orcid` on authors; etc. The parser
# already knows the queried entity (`self._entity`), and the properties registry
# (`core/properties.py ENTITY_PROPERTIES`) is the entity-scoped source of truth
# for which column a name resolves to ON THAT ENTITY — keyed by each property's
# `display_name`/`aliases` (the gate `test_oql_render_word_equals_registry_
# display_name` keeps the OQL word == the works display_name, so the same friendly
# word indexes the entity-correct column on every entity). So: after the curated
# `match_field` gives us a Field's OQL render/parse *mechanics* (kind, casing),
# we re-point its *column* at the entity-correct one. Drift-proof:
# no hand-kept per-field override table — the registry's own display_names drive it.
_ENTITY_WORD_INDEX_CACHE: Dict[str, Dict[str, str]] = {}


def _entity_word_index(entity: str) -> Dict[str, str]:
    """{display_name/alias (lower) -> column_id} for one entity, from the registry.
    Empty dict if the entity/registry is unavailable (keeps oql_lang importable in
    lightweight contexts without the engine properties registry)."""
    if entity in _ENTITY_WORD_INDEX_CACHE:
        return _ENTITY_WORD_INDEX_CACHE[entity]
    try:
        from core.properties import get_entity_properties
        props = get_entity_properties(entity) or {}
    except Exception:
        props = {}
    idx: Dict[str, str] = {}
    for cid, prop in props.items():
        names = [getattr(prop, "display_name", "")] + list(getattr(prop, "aliases", []) or [])
        for name in names:
            if name:
                idx.setdefault(name.lower(), cid)
    _ENTITY_WORD_INDEX_CACHE[entity] = idx
    return idx


def _entity_resolve_field(fld: "Field", entity: Optional[str]) -> "Field":
    """Re-point a curated Field's column at the column that actually exists on
    `entity` for the same friendly word, leaving every other (render/parse)
    attribute untouched. A no-op when the curated column already exists on the
    entity (the works common case → byte-identical strict behavior), or when there
    is no entity, no registry, or no entity-correct column (→ the curated column
    flows through and the validator gates it as `invalid_column`). Booleans ARE
    resolved here too (a bool homonym like `CWTS core source` → works
    `primary_location.source.is_core` vs sources bare `is_core`); the bool clause
    parser calls this after matching the phrasing (oxjob #406 1c)."""
    if not entity or fld.kind in ("search", "collection"):
        return fld
    try:
        from core.properties import get_entity_properties
        props = get_entity_properties(entity) or {}
    except Exception:
        return fld
    if not props or fld.column in props:
        return fld
    col = _entity_word_index(entity).get(fld.oql.lower())
    if col and col != fld.column:
        return replace(fld, column=col)
    return fld


# (The entity-homonym (#406) and alias-canonical (#455) render-side mappings
#  are tiers 1 and 2 of `_build_by_column()`, the single `_BY_COLUMN` build
#  site below.)


# Boolean sentence phrasings (oxjob #428) were removed in #363: booleans are now
# ordinary `<name> is true|false` clauses, so there are no curated bool_true/
# bool_false sentences and nothing for the /properties catalog to copy.


# --- entity-aware GUI-faceted registry fallback (oxjob #406, increment 1b) ---
# Part B coverage: a NON-works column with no curated `_FIELDS` surface and no
# homonym (e.g. `issn_l`/"ISSN-L" on sources, `works_count`/"works count" on
# authors, `summary_stats.h_index`/"h-index") gains an OQL surface here. Scope =
# the GUI-faceted subset per entity (`input_alias_columns.GUI_FACETED_COLUMNS_BY_
# ENTITY`, Jason's GUI-parity lens), synthesized from the registry's own metadata
# so the friendly word == the engine `display_name`. Parsed by display_name, alias,
# OR raw column_id (oxurl-fluent users), greedily (multi-word labels like "works
# count"). Booleans are EXCLUDED — their OQL render needs a curated sentence
# template, so they're surfaced via `_FIELDS` _f(...) entries, not here.
_ENTITY_FALLBACK_CACHE: Dict[str, Dict[str, "Field"]] = {}


def _build_entity_fallback(entity: str) -> Dict[str, "Field"]:
    try:
        from core.properties import get_entity_properties
        from query_translation.input_alias_columns import (
            GUI_FACETED_COLUMNS_BY_ENTITY, INPUT_ALIAS_COLUMNS)
        props = get_entity_properties(entity) or {}
    except Exception:
        return {}
    # works uses its existing GUI/docs allowlist; the non-works entities use the
    # per-entity GUI-faceted snapshot. On WORKS this fallback exists ONLY to let the
    # registry own a curated column's input aliases — so a friendly alias can be
    # DROPPED from `_FIELDS` (it lives in `core/display_names.py`) and still parse
    # (oxjob #406 1c cleanup). It deliberately does NOT surface uncurated works
    # columns (those keep the raw column-id path + raw render) — see the works guard.
    is_works = entity == "works"
    allow = INPUT_ALIAS_COLUMNS if is_works else GUI_FACETED_COLUMNS_BY_ENTITY.get(entity, frozenset())
    out: Dict[str, Field] = {}
    for cid in allow:
        prop = props.get(cid)
        if prop is None:
            continue
        ops = set(getattr(prop, "operators", []) or [])
        if "search" in ops or "collection" in ops:
            continue
        # Reuse the curated Field when one exists — full fidelity (kind, casing,
        # and for booleans the sentence phrasing), so a removed alias
        # re-resolves to EXACTLY the curated behavior.
        curated = _BY_COLUMN.get(cid)
        if curated is not None and curated.kind not in ("search", "collection"):
            fld = curated
        elif is_works:
            continue                  # works: don't surface uncurated columns here
        else:
            kind = _registry_kind(prop, surface_rich_kinds=True)
            if kind is None:
                continue              # uncurated bool needs phrasing -> not surfaced here
            dn0 = getattr(prop, "display_name", None)
            if not dn0:
                continue
            fld = Field(column=cid, kind=kind, oql=dn0, casing="",
                        is_float=(kind == "num" and "mean_citedness" in cid))
        # parse by display_name, registry aliases, and the raw column_id
        for key in [getattr(prop, "display_name", "")] + list(getattr(prop, "aliases", []) or []) + [cid]:
            if key:
                out.setdefault(key.lower(), fld)
    return out


def _entity_fallback(entity: str) -> Dict[str, "Field"]:
    if entity not in _ENTITY_FALLBACK_CACHE:
        _ENTITY_FALLBACK_CACHE[entity] = _build_entity_fallback(entity)
    return _ENTITY_FALLBACK_CACHE[entity]


def match_entity_fallback(toks: List[Tok], i: int, entity: Optional[str]
                          ) -> Optional[Tuple[str, "Field", int]]:
    """Greedy longest GUI-faceted-registry match (up to 4 words) at ``toks[i]`` for
    `entity`. Returns ``(spelling, Field, n_tokens)`` or ``None``. On works the index
    holds ONLY curated columns' registry aliases (so a dropped `_FIELDS` alias still
    parses); uncurated works columns stay on the `_registry_fallback_field` path."""
    if not entity:
        return None
    index = _entity_fallback(entity)
    if not index:
        return None
    best: Optional[Field] = None
    best_len = 0
    parts: List[str] = []
    for k in range(0, 4):
        t = toks[i + k] if i + k < len(toks) else None
        if not t or t.kind != "WORD":
            break
        parts.append(t.val)
        key = " ".join(parts).lower()
        if key in index:
            best = index[key]
            best_len = k + 1
    if best is None:
        return None
    spelling = " ".join(toks[i + k].val for k in range(best_len))
    return spelling, best, best_len


# --- the ONE `_BY_COLUMN` build (oxjob #567) --------------------------------
# Every render-side column->Field mapping is claimed HERE, in one pass with an
# EXPLICIT precedence ladder — nothing else writes `_BY_COLUMN`. Before #567
# this was a base pass plus three sequential `setdefault` augment passes whose
# net result silently depended on execution order and on `_FIELDS` declaration
# order. Now each mapping is a *claim* at a named precedence tier: a stronger
# (lower) tier always wins, and two DIFFERENT claims at a column's winning
# tier raise at import instead of resolving by iteration order.
#
# The tiers (strongest first):
#   0 curated         — a `_f(...)` row's own column, plus the deprecated
#                       `default` -> fulltext alias (#374).
#   1 homonym         — the entity-correct column a curated word resolves to
#                       on some entity (#406). `_BY_COLUMN` is a GLOBAL map
#                       keyed on each curated Field's works-default column, so
#                       e.g. authors' `orcid` / sources' `issn` would render
#                       RAW without these claims. Mapping back to the SAME
#                       curated Field guarantees the render word re-parses to
#                       this exact column — the round-trip holds by
#                       construction; columns with no parseable word render
#                       raw.
#   2 alias-canonical — the CANONICAL column_id of a curated Field whose
#                       column spelling is a filter alias (#455): parse-time
#                       canonicalization means OQOs carry the canonical id,
#                       which must render the curated word, not raw. Render-
#                       only — no registry display_name / PROPERTIES_VERSION
#                       impact.
#   3 entity-fallback — GUI-faceted non-works columns synthesized from the
#                       registry (#406 1b), so e.g. sources' `issn_l` renders
#                       "ISSN-L". SAFETY GATE: parsing a fallback word is
#                       entity-SCOPED but this map is GLOBAL, so a column only
#                       renders its friendly word when that word parses back
#                       on EVERY in-scope entity that has the column
#                       (`_faceted_everywhere`) — e.g. `works_count` is
#                       GUI-faceted only on funders, so it renders RAW (the
#                       column_id, which always round-trips).
def _build_by_column() -> None:
    tier_of: Dict[str, int] = {}

    def claim(tier: int, column: str, fld: "Field", source: str) -> None:
        cur = _BY_COLUMN.get(column)
        if cur is None:
            _BY_COLUMN[column] = fld
            tier_of[column] = tier
        elif tier_of[column] == tier and cur != fld:
            raise AssertionError(
                f"_BY_COLUMN conflict: column {column!r} claimed at tier {tier}"
                f" by both {cur.oql!r} and {fld.oql!r} ({source}). Resolve it"
                " explicitly (curate one row / split the tier) — never by"
                " declaration or iteration order.")
        # else: a stronger (lower) tier already owns the column.

    # Tier 0 — curated rows.
    for _spellings, fld in _FIELDS:
        claim(0, fld.column, fld, "curated _FIELDS row")
    # default.search is the deprecated alias of fulltext.search (oxjob #374):
    # render any stray `default` column (e.g. from an external URL->OQO) to
    # the canonical "fulltext" word so it round-trips into fulltext.search.
    claim(0, "default", _BY_COLUMN["fulltext"], "deprecated default alias")

    # Tiers 1-3 need the engine registry; without it (lightweight contexts)
    # the curated map alone stands.
    try:
        from core.properties import ENTITY_PROPERTIES, canonicalize_column_id
        from query_translation.input_alias_columns import GUI_FACETED_COLUMNS_BY_ENTITY
        entities = list(ENTITY_PROPERTIES.keys())
    except Exception:
        return
    # works first, so when several entities make the same-tier claim on one
    # column, works' claim is the one recorded (they must agree anyway —
    # `claim` raises on a genuine same-tier disagreement).
    order = ["works"] + [e for e in entities if e != "works"]

    for ent in order:                       # Tier 1 — homonyms (#406)
        for _spellings, fld in _FIELDS:
            if fld.kind in ("search", "collection"):
                continue
            resolved = _entity_resolve_field(fld, ent)
            if resolved.column != fld.column:
                claim(1, resolved.column, fld,
                      f"homonym of {fld.oql!r} on {ent}")

    for ent in order:                       # Tier 2 — alias canonicals (#455)
        for _spellings, fld in _FIELDS:
            if fld.kind in ("search", "collection"):
                continue
            canon = canonicalize_column_id(fld.column, ent)
            if canon != fld.column:
                claim(2, canon, fld,
                      f"alias-canonical of {fld.oql!r} on {ent}")

    def _faceted_everywhere(cid: str) -> bool:
        # Only entities in fallback SCOPE (those with a GUI-faceted allowlist)
        # can parse a fallback word, so only they constrain whether a friendly
        # render round-trips. An in-scope entity that HAS the column but
        # doesn't facet it (e.g. authors has `works_count` but doesn't
        # surface it) forces raw render.
        for e in GUI_FACETED_COLUMNS_BY_ENTITY:
            props = ENTITY_PROPERTIES.get(e) or {}
            if cid in props and cid not in GUI_FACETED_COLUMNS_BY_ENTITY[e]:
                return False
        return True

    for ent in entities:                    # Tier 3 — entity fallback (#406 1b)
        if ent == "works":
            continue
        # `_entity_fallback()` builds (and caches) each entity's index against
        # `_BY_COLUMN` *as of this claim* — curated Fields (including tier-1/2
        # keys) are reused for full fidelity, so the interleaving of index
        # builds with claims is deliberate, frozen behavior.
        for cid, fld in _entity_fallback(ent).items():
            # only the canonical column_id key (fld.column) seeds the reverse
            # map, and only when the friendly word renders safely everywhere.
            if cid == fld.column and _faceted_everywhere(cid):
                claim(3, cid, fld, f"entity fallback on {ent}")


_build_by_column()


# --- registry-derived namespace resolution (oxjob #565) ----------------------
# "Which entity namespace does this column's value belong to" used to live in
# THREE hand-maintained maps (renderer `_RESOLVE_NAMESPACE`, editor
# `_COLUMN_AUTOCOMPLETE_ENTITY`, enum `_ENUM_COLUMN_NAMESPACE`) plus a fourth
# boolean copy (`Field.resolves_name`) — the #418/#455 silent-drift class
# (every new id column rendered bare / got no autocomplete until someone
# updated all four). The registry already knows the answer:
# `Property.entity_type` — exactly how the validator resolves namespaces.
# Derivation, strongest first:
#   1. override — the relation-edge oddballs the registry can't carry (below)
#   2. direct   — `ENTITY_PROPERTIES[entity][column_id].entity_type`,
#                 checking the preferred `entity` first, then works, then
#                 every entity (spellings are disjoint across entities in
#                 practice — the #406 exceptions are all overridden/excluded)
#   3. homonym  — a column with no direct entity_type whose `_BY_COLUMN`
#                 Field is the entity-correct spelling of a curated word
#                 (#406): resolve the word per entity and read the resolved
#                 column's entity_type (topics' `domain.id` -> works'
#                 `primary_topic.domain.id` -> "domains"; locations'
#                 `source_id` -> `primary_location.source.id` -> "sources").

_ENTITY_TYPE_OVERRIDES: Dict[str, Optional[str]] = {
    # Citation/relation edges reference a WORK. The registry deliberately
    # carries no entity_type on them — entity_type also grants collection
    # resolution (#394), a semantic decision not (yet) taken for edges.
    "cited_by": "works",
    "cites": "works",
    "referenced_works": "works",
    "related_to": "works",
}

# A row's OWN id never name-annotates: a resolver miss there means "no name
# for this kind of column", not "entity not found" (#418) — and bare `id`
# means a different entity on every entity page, so a global answer would lie.
_SELF_ID_COLUMNS = {"ids.openalex", "id", "openalex", "openalex_id"}

# entity_types whose values are self-describing slugs (`article`, `gold`,
# `cc-by`): annotating them (`article [article]`) is noise, so they carry NO
# annotation namespace. They still validate and autocomplete through their
# closed vocab (validator.CLOSED_VOCAB_NAMESPACE ∘ entity_type_for_column).
_READABLE_SLUG_TYPES = {"work-types", "oa-statuses", "source-types",
                        "institution-types", "licenses"}

_ENTITY_TYPE_CACHE: Dict[Tuple[str, Optional[str]], Optional[str]] = {}


def entity_type_for_column(column_id: str, entity: Optional[str] = None
                           ) -> Optional[str]:
    """The registry `entity_type` of `column_id`'s values (raw: `work-types`,
    `countries`, `authors`, …), or None. The single derived source behind every
    column→namespace consumer (renderer annotation, editor autocomplete, enum
    suggestions). `entity` is a preference, not a scope — a column the given
    entity doesn't type still resolves via works / the other entities, matching
    the entity-blind behavior of the hand maps this replaces."""
    key = (column_id, entity)
    if key in _ENTITY_TYPE_CACHE:
        return _ENTITY_TYPE_CACHE[key]
    _ENTITY_TYPE_CACHE[key] = et = _derive_entity_type(column_id, entity)
    return et


def _derive_entity_type(column_id: str, entity: Optional[str]) -> Optional[str]:
    if column_id in _ENTITY_TYPE_OVERRIDES:
        return _ENTITY_TYPE_OVERRIDES[column_id]
    try:
        from core.properties import ENTITY_PROPERTIES
    except Exception:
        return None
    order = []
    for e in ([entity] if entity else []) + ["works"] + list(ENTITY_PROPERTIES):
        if e in ENTITY_PROPERTIES and e not in order:
            order.append(e)
    for e in order:
        prop = ENTITY_PROPERTIES[e].get(column_id)
        et = getattr(prop, "entity_type", None) if prop is not None else None
        if et:
            return et
    # Homonym fallback (#406): this column may be the entity-correct spelling
    # of a curated word — read the entity_type off the column that word
    # resolves to where it IS typed.
    fld = _BY_COLUMN.get(column_id)
    if fld is None or fld.kind in ("search", "collection"):
        return None
    candidates = [fld.column] if fld.column != column_id else []
    for e in order:
        resolved_col = _entity_resolve_field(fld, e).column
        if resolved_col != column_id and resolved_col not in candidates:
            candidates.append(resolved_col)
    for col in candidates:
        for e in order:
            prop = ENTITY_PROPERTIES[e].get(col)
            et = getattr(prop, "entity_type", None) if prop is not None else None
            if et:
                return et
    return None


def namespace_for_column(column_id: str, entity: Optional[str] = None
                         ) -> Optional[str]:
    """The name-ANNOTATION namespace for `column_id`, or None when its values
    never annotate (self-ids, readable slugs, un-namespaced columns). Non-None
    means: the renderer looks values up as `<namespace>/<short_id>` (native ES
    entities + the config/*.yaml closed vocabs), annotates hits `[Name]`, and
    marks misses `[no entity found]` (#418)."""
    if column_id in _SELF_ID_COLUMNS:
        return None
    fld = _BY_COLUMN.get(column_id)
    if fld is not None and fld.kind in ("search", "collection"):
        # search terms aren't entity values; a collection column's values are
        # opaque col_… refs (its entity_type exists for collection RESOLUTION,
        # not display names).
        return None
    et = entity_type_for_column(column_id, entity)
    if et is None or et in _READABLE_SLUG_TYPES:
        return None
    # the one entity_type whose config namespace differs is work-types->types,
    # and it's slug-excluded above — so namespace == entity_type here.
    return et


def match_operator(toks: List[Tok], i: int) -> Optional[Tuple[str, int, bool]]:
    """Greedy operator match at ``toks[i]``.

    Returns ``(op, n_tokens, complete)`` or ``None`` if the token can't begin an
    operator. For every ``complete=True`` result, ``n_tokens``/``op`` are exactly what
    the fail-fast parser consumes/returns. ``complete=False`` means a multi-word
    operator is still being typed (e.g. ``is similar`` without ``to``) — the editor
    treats that as "keep typing"; the parser falls back to the shorter complete
    operator (``is``) or raises.

    NOTE: the old value-list openers ``is any of`` / ``is in`` / their negations are
    GONE — value lists use the parenthesized ``is (a or b)`` / ``is (a and b)`` form,
    parsed inside the value/search body, not via a special operator. ``is [not] in
    collection`` (the live Collections operator) is unrelated and preserved below.
    """
    if i >= len(toks):
        return None
    t = toks[i]
    if t.kind == "OP":  # > >= < <=
        return t.val, 1, True
    if t.kind != "WORD":
        return None

    def w(k: int) -> Optional[str]:
        tk = toks[i + k] if i + k < len(toks) else None
        return tk.val.lower() if tk and tk.kind == "WORD" else None

    w0 = w(0)
    if w0 == "has":
        return "has", 1, True
    if w0 == "is":
        if w(1) == "similar":
            if w(2) == "to":
                return "similar", 3, True
            return "similar", 2, False                # `is similar` — still typing
        if w(1) == "not":
            # `is not in collection` (the live Collections operator) — the bare
            # `is not in` list form was removed; `in` then falls through as a value.
            if w(2) == "in" and w(3) == "collection":
                return "nincoll", 4, True
            return "isnot", 2, True                    # `is not` (scalar)
        if w(1) == "in" and w(2) == "collection":
            return "incoll", 3, True                   # `is in collection`
        return "is", 1, True
    if w0 in ("does", "doesn't", "doesnt"):
        j = 1 if w(1) == "not" else 0
        if w(1 + j) == "have":
            return "nhas", 2 + j, True
        return "nhas", 1 + j, False                    # `does not` — typing
    return None


# ---------------------------------------------------------------------------
# Row-subject verb-phrase leaves (oxjob #557).
# A grammar CATEGORY, not a one-off: the subject is the queried row itself —
# the pronoun `it` — and a verb phrase names a relation column; the value is
# the usual parenthesized group. Canonical renders (contraction included):
#     it cites (W…)          -> referenced_works   (this work cites W)
#     it's cited by (W…)     -> cited_by           (this work is cited by W)
#     it's related to (W…)   -> related_to
# Negation is VALUE-LEVEL ONLY (charter decision 23): `it cites (not W…)` —
# there is no `doesn't cite`/`isn't cited by` verb form; leaves stay
# affirmative. Input is forgiving: `it is cited by`, `its cited by` (dropped
# apostrophe), and the legacy field-word forms (`cites is`, `references is`,
# `cited by is`, `related to is`) all still parse; everything converges on the
# canonical renders above. Existing cousin: `work is in collection (col_…)` —
# a noun-subject predicate; migrating it to `it's in collection (…)` is a
# separate decision (EXPLORE.md decision 2), deliberately not bundled here.
# ---------------------------------------------------------------------------
_ROW_SUBJECT_PRONOUNS = ("it", "it's", "its")

# (verb-phrase words, column, needs_copula): after bare `it` the copula is a
# separate token (`it is cited by`); `it's`/`its` embed it. `cites` never
# takes one (`it's cites` is rejected).
_ROW_SUBJECT_VERBS = (
    (("cites",), "referenced_works", False),
    (("cited", "by"), "cited_by", True),
    (("related", "to"), "related_to", True),
)

# column -> (subject seg, verb/operator seg, bare chip word). The first two
# concatenate (+ the parenthesized value group) to the canonical clause text;
# the bare word is the GUI-chip label carried in ClauseMeta.column_display_name.
_ROW_SUBJECT_RENDER = {
    "referenced_works": ("it", " cites ", "cites"),
    "cited_by": ("it's", " cited by ", "cited by"),
    "related_to": ("it's", " related to ", "related to"),
}


def match_row_subject(toks: List[Tok], i: int
                      ) -> Optional[Tuple[Optional[str], int, bool]]:
    """Greedy row-subject verb-phrase match at ``toks[i]`` (oxjob #557).

    Returns ``(column, n_tokens, complete)``, or ``None`` when ``toks[i]`` is
    not a row-subject pronoun at all. ``complete=False`` means the pronoun is
    there but the verb phrase is absent or partial (still being typed): the
    editor offers verb-phrase completions (CTX_VERB); the strict parser raises
    OQL_BAD_VERB_PHRASE. Mirrors ``match_operator``'s contract so the parser,
    the clause-boundary heuristics, and the editor share ONE matcher.
    """
    t = toks[i] if i < len(toks) else None
    if t is None or t.kind != "WORD":
        return None
    # normalize the curly apostrophe (U+2019) — macOS/iOS smart punctuation
    # auto-curls `it's` on retype, and the canonical render contains one
    subj = t.val.lower().replace("’", "'")
    if subj not in _ROW_SUBJECT_PRONOUNS:
        return None

    def w(k: int) -> Optional[str]:
        tk = toks[i + k] if i + k < len(toks) else None
        return tk.val.lower() if tk is not None and tk.kind == "WORD" else None

    has_copula = subj in ("it's", "its")
    j = 1
    if not has_copula and w(1) == "is":
        j = 2                       # `it is cited by` — copula as its own token
        has_copula = True
    for words, column, needs_copula in _ROW_SUBJECT_VERBS:
        if needs_copula != has_copula:
            continue
        k = 0
        while k < len(words) and w(j + k) == words[k]:
            k += 1
        if k == len(words):
            return column, j + k, True
    return None, j, False           # pronoun seen, verb phrase absent/partial


# ---------------------------------------------------------------------------
# Editor-context grammar-state categories (oxjob #363, charter decision 15).
# These are the canonical strings the dual-mode parser reports at a cursor; the
# editor presentation layer (`oql_context.py`) re-exports them and maps them to
# suggestion lists. Defined HERE so the parser is the single source of grammar truth.
# ---------------------------------------------------------------------------
CTX_ENTITY = "entity"
CTX_FIELD = "field"
CTX_OPERATOR = "operator"
CTX_VERB = "verb-phrase"   # after the row-subject pronoun `it`/`it's` (oxjob #557)
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
        # --- dual-mode (editor-context) state (oxjob #363, decision 15) ---
        # `_ctx_mode` is False for all production parsing, so every `_want(...)`
        # call and every `if self._ctx_mode` branch below is an inert no-op on the
        # strict path — strict behavior is byte-identical (locked by tests/oql).
        self._ctx_mode = False
        self._ctx = None          # (category, payload) recorded at the cursor
        self._entity = None       # resolved get_rows entity (for the context reply)
        self._cur_fld = None      # field of the clause currently being parsed
        self._in_list = False     # are we inside a parenthesized value list?
        self._directive = None    # "group" when inside a directive
        # --- editor sectioned-menu bookkeeping (oxjob #357, ctx-mode only) ---
        # Spans of the most-recent TOP-LEVEL operand, recorded as token indices so the
        # post-connective FIELD context can describe the "sibling" clause (the one the
        # cursor sits after) for the editor's "add another value" auto-paren rewrite.
        # Pure bookkeeping — assigned on every parse but only READ in context mode.
        self._last_operand_span = None    # (start_tok_i, end_tok_i) of the last operand
        self._last_operand_simple = False  # was it a bare `field op value` clause?
        self._last_value_start_i = None   # token index where that clause's value began
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
        # Optional corpus selector parenthetical right after the entity (#481),
        # e.g. `works (all corpora) where ...`. Default "core" when absent.
        corpus = self._parse_corpus_opt()
        filters: List[FilterType] = []
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
            if t.kind == "WORD" and t.val.lower() == "group" and self.word_is("by", k=1):
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
                               'queries are: <entity> [where <conditions>] '
                               '[group by ...] [sample N]', t.pos)
        # Collapse alias spellings to one canonical identity at the parse boundary
        # (#455) — covers leaf and group uniformly, so the leaf path's entity-resolve
        # and the (previously un-canonicalized) group path both emit the canonical
        # column_id. Idempotent; downstream sees one spelling.
        return canonicalize_oqo_column_ids(
            OQO(get_rows=entity, corpus=corpus, filter_rows=filters,
                group_by=group_by, sample=sample, seed=seed))

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

    def _operand_tracked(self) -> FilterType:
        """`_operand()` wrapped to record the operand's token span + whether it was a
        bare `field op value` clause (vs a `(...)` group / `not …`) — bookkeeping the
        post-connective sectioned-menu context reads (oxjob #357). Reset-then-parse so
        a non-simple operand can't leave a stale `_last_value_start_i` behind."""
        start_i = self.i
        self._last_operand_simple = False
        self._last_value_start_i = None
        out = self._operand()
        self._last_operand_span = (start_i, self.i)
        return out

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
                if t.kind == "WORD" and t.val.lower() in ("group", "sample"):
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
            return two.replace(" ", "-")
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

    def _parse_corpus_opt(self) -> str:
        """Optional corpus selector parenthetical immediately after the entity
        (#481): `(core corpus)` / `(core)` / `(all corpora)` / `(all)` /
        `(expansion corpus)` / `(expansion)` / `(xpac)` / `(xpac corpus)`.

        Returns the canonical corpus value ("core" when no parenthetical). A `(`
        at this position is unambiguous — nothing else is valid between the
        entity and `where`."""
        self._skip_annot()
        t = self.peek()
        if t is None or t.kind != "LP":
            return "core"
        open_pos = t.pos
        self.next()  # consume "("
        words: List[str] = []
        while True:
            self._skip_annot()
            tk = self.peek()
            if tk is None:
                raise oql_error("OQL_BAD_CORPUS",
                               "the corpus parenthetical was opened but never closed",
                               "e.g. works (all corpora) where ...", open_pos)
            if tk.kind == "RP":
                self.next()
                break
            if tk.kind != "WORD":
                raise oql_error("OQL_BAD_CORPUS",
                               f'unexpected "{tk.val}" inside the corpus parenthetical',
                               "e.g. works (all corpora) where ...", tk.pos)
            words.append(tk.val)
            self.next()
        phrase = " ".join(words)
        corpus = normalize_corpus(phrase)
        if corpus is None:
            raise oql_error("OQL_BAD_CORPUS",
                           f'"({phrase})" is not a corpus',
                           "use (core corpus), (expansion corpus), or (all corpora)",
                           open_pos)
        return corpus

    # -- boolean expression; mixed and/or resolved by precedence (AND > OR) --
    def _parse_expr(self, top=False) -> FilterType:
        operands = [self._operand_tracked()]
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
                    operands.append(self._operand_tracked())  # recover: implicit AND
                    continue
                self._adjacency_error(t)
            if t.kind == "WORD" and t.val.lower() in _CONNECTIVES:
                conn = t.val.lower()
                conns.append(conn)
                # Snapshot the sibling clause (the operand the cursor sits after)
                # BEFORE we consume the connective + parse the next operand, so the
                # post-connective FIELD context can describe it for the editor's
                # "add another value" auto-paren rewrite (oxjob #357).
                sib_span, sib_simple = self._last_operand_span, self._last_operand_simple
                sib_fld, sib_val_start = self._cur_fld, self._last_value_start_i
                self.next()
                # cursor right after the connective (empty slot) -> sectioned-menu
                # FIELD context carrying the sibling clause (no-op unless ctx_mode +
                # out of tokens; strict path untouched).
                self._want(CTX_FIELD, after_connective=conn, sibling_fld=sib_fld,
                           sibling_simple=sib_simple, sibling_clause_span=sib_span,
                           sibling_value_start=sib_val_start)
                operands.append(self._operand_tracked())
                continue
            # directive keywords end the where-expression
            if t.kind == "WORD" and t.val.lower() in ("group", "sample"):
                break
            # anything else with no connective = implicit adjacency
            if self._recover_mode:
                self._diagnostics.append(self._adjacency_err(t))
                operands.append(self._operand_tracked())  # recover: implicit AND
                continue
            self._adjacency_error(t)
        # Mixed and/or at one level is NOT an error — it's resolved by the standard
        # precedence AND > OR (WoS/Scopus/boolean-algebra convention). The canonical
        # render re-parenthesizes the grouping so it's never implicit on the page.
        return _precedence_tree(operands, conns)

    def _adjacency_error(self, t: Tok):
        raise self._adjacency_err(t)

    def _adjacency_err(self, t: Tok) -> OQLError:
        return oql_error("OQL_IMPLICIT_ADJACENCY",
                        f'two conditions with no AND/OR between them (near "{t.val}")',
                        'insert an explicit AND or OR', t.pos)

    def _consume_not(self, t: Tok):
        """Consume a bare `not` prefix keyword (charter decision 23). `not` is a
        prefix operator that negates the single value-node / operand that follows
        it — no parentheses required (`not FR`, `not dog`, `not col_x`). A
        `not (a or b)` still works: the following `(...)` parses as the operand
        and the canonicalizer pushes negation down to the leaves (NNF). Precedence
        is the SR/PubMed convention — `not` binds the next operand only, so
        `not a or b` = `(not a) or b`. Leaves the cursor right after `not` so the
        caller's normal operand/group/scalar parse handles the argument."""
        self.next()  # consume 'not'
        self._skip_annot()

    def _parse_operand(self) -> FilterType:
        self._skip_annot()
        # An empty operand slot (start of conditions, or just after "(" / a
        # connective) expects a field clause.
        self._want(CTX_FIELD)
        t = self.peek()
        if t is None:
            raise oql_error("OQL_EMPTY", "expected a condition", "")
        if t.kind == "WORD" and t.val.lower() == "not":
            self._consume_not(t)              # bare prefix `not` (decision 23)
            inner = self._parse_operand()     # negate the next operand (clause/group)
            self._last_operand_simple = False  # negated -> not a plain clause (#357)
            return _negate(inner)
        if t.kind == "LP":
            self.next()
            e = self._parse_expr()
            self._expect_rp()
            self._last_operand_simple = False  # a (...) group -> not a plain clause (#357)
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
        # A bare `field op value` clause is the one shape the sectioned menu can
        # "add another value" to via an auto-paren rewrite (oxjob #357). Bool/search
        # clauses also pass here but leave `_last_value_start_i` None, so the editor
        # gates them out (no enum value list to extend).
        self._last_operand_simple = True
        # row-subject leaf: `it cites (…)` / `it's cited by (…)` / `it's related
        # to (…)` — the pronoun claims the field slot (oxjob #557).
        rs = match_row_subject(self.toks, self.i)
        if rs is not None:
            return self._parse_row_subject_clause(rs)
        field, fld = self._parse_field()
        self._cur_fld = fld
        # a complete field with the cursor right after it -> operator slot
        self._want(CTX_OPERATOR, fld=fld)
        op = self._parse_operator()
        if fld.kind == "search":
            if op == "similar":
                return self._parse_semantic(fld)
            if op not in ("has", "nhas"):
                raise oql_error("OQL_BAD_OPERATOR_FOR_FIELD",
                               f'search field "{field}" needs "has" (not "{op}")',
                               'use: <field> has <terms>')
            tree = self._parse_search_value(fld.column)
            if op == "nhas":
                tree = _negate(tree)
            return tree
        # non-search
        if op in ("has", "nhas", "similar"):
            raise oql_error("OQL_BAD_OPERATOR_FOR_FIELD",
                           f'field "{field}" does not support "{op}"',
                           'use "is" / a comparison')
        return self._parse_value_clause(field, fld, op)

    def _parse_row_subject_clause(self, m) -> FilterType:
        """One row-subject verb-phrase leaf (oxjob #557): the pronoun + verb
        phrase select a relation column; the value clause is the ordinary `is`
        machinery (parenthesized groups, value-level `not`, `unknown`)."""
        column, n, complete = m
        t = self.peek()
        if not complete:
            # The pronoun is there but the verb phrase is absent/partial. Editor:
            # if everything from the pronoun to the cursor is still (partial)
            # phrase words — nothing but WORDs, within the longest phrase's span —
            # this is the verb-phrase slot (mirrors the incomplete-operator
            # special case in `_parse_operator`). Strict: a targeted error.
            rest = self.toks[self.i + 1:]
            if (self._ctx_mode and len(rest) <= 3
                    and all(tk.kind == "WORD" for tk in rest)):
                # same curly-apostrophe normalization as match_row_subject, so
                # the editor's per-subject verb suggestions match `it’s` too
                self._ctx = (CTX_VERB,
                             {"subject": t.val.lower().replace("’", "'"),
                              "phrase_start_i": self.i + 1})
                raise _CtxFound()
            raise oql_error("OQL_BAD_VERB_PHRASE",
                           f'expected a relation verb phrase after "{t.val}"',
                           None, t.pos)
        fld = _entity_resolve_field(_BY_COLUMN[column], self._entity)
        self._cur_fld = fld
        self.i += n
        subj, verb, _bare = _ROW_SUBJECT_RENDER[column]
        return self._parse_value_clause(f"{subj}{verb.rstrip()}", fld, "is")

    def _parse_field(self) -> Tuple[str, Field]:
        # an empty / partially-typed field slot at the cursor
        self._want(CTX_FIELD)
        # greedy longest alias match (up to 4 words) — shared with the editor walker
        m = match_field(self.toks, self.i)
        # Non-works GUI-faceted registry field (oxjob #406 1b): a non-works column's
        # display_name / alias / raw id (e.g. `issn-l` on sources, `works count` on
        # funders). LONGEST-match wins over the curated matcher — a multi-word label
        # ("works count") must beat a curated word that is merely its first token
        # ("works", the collection alias); on a tie the curated match is preferred.
        # Skipped in ctx_mode so the editor still offers curated completions.
        if not self._ctx_mode:
            em = match_entity_fallback(self.toks, self.i, self._entity)
            if em is not None and (m is None or em[2] > m[2]):
                spelling, efld, en = em
                self.i += en
                return spelling, efld
        if m is None:
            # Fallback B: a single WORD that is a raw works-registry column_id is
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
        fld = _entity_resolve_field(fld, self._entity)   # entity-correct the column (#406)
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
            op, n, _complete = m
            self.i += n
            return op
        # Legacy `contains` was renamed to `has` (#363 decision 27). It's a HARD
        # error (no lenient parse), with a fix-it echoing the new keyword — the
        # same greenfield, no-back-compat stance as decisions 23 & 24.
        if t.kind == "WORD" and t.val.lower() == "contains":
            raise oql_error("OQL_CONTAINS_RENAMED",
                           "`contains` was renamed to `has`",
                           "use: <field> has <terms>", t.pos)
        # Not a complete operator. Replicate the fail-fast fallbacks: a partial
        # `is …` (e.g. `is any`, `is similar`) degrades to the bare `is` operator
        # (the tail becomes the value); a partial `does …` has no shorter form, so
        # it's a missing-operator error; anything else isn't an operator at all.
        if t.kind == "WORD" and t.val.lower() == "is":
            self.next()
            return "is"
        if t.kind == "WORD" and t.val.lower() in ("does", "doesn't", "doesnt"):
            # `does not contain` is the renamed-away negation sugar; `does not have`
            # is accepted above (the complete `nhas` operator). Echo the fix-it.
            nxt = self.toks[self.i + 1] if self.i + 1 < len(self.toks) else None
            after = self.i + (2 if nxt and nxt.kind == "WORD"
                              and nxt.val.lower() == "not" else 1)
            af = self.toks[after] if after < len(self.toks) else None
            if af and af.kind == "WORD" and af.val.lower() == "contain":
                raise oql_error("OQL_CONTAINS_RENAMED",
                               "`does not contain` was renamed to `does not have`",
                               "use: <field> does not have <terms>", t.pos)
            raise oql_error("OQL_MISSING_OPERATOR", 'expected "does not have"')
        # Bare row-subject verb form (#557, EXPLORE decision 6): for the relation
        # columns the field word IS the verb — `cites (W…)`, `cited by (W…)`,
        # `related to (W…)` — so a value group directly after the field word
        # implies `is`. Render restores the canonical pronoun form (`it cites
        # (…)`). Row-subject columns ONLY; `year (2020)` stays an error.
        if (t.kind == "LP" and self._cur_fld is not None
                and self._cur_fld.column in _ROW_SUBJECT_RENDER):
            return "is"
        raise oql_error("OQL_MISSING_OPERATOR",
                       f'expected an operator, got "{t.val}"', None, t.pos)

    def _open_scalar_group(self) -> bool:
        """Consume a `(` opening a SCALAR value group, if present (#554 —
        canonical form always parenthesizes a condition's value, so every
        scalar-domain operator accepts an exactly-one-atom group). Returns
        whether a group was opened; the caller closes it via
        `_close_scalar_group`."""
        t = self.peek()
        if t is None or t.kind != "LP":
            return False
        self.next()
        self._skip_annot()
        return True

    def _close_scalar_group(self, one_value_msg: str, one_value_fixit: str):
        """Close an exactly-one-atom scalar group: anything but `)` after the
        single atom is a loud arity diagnostic (#554 — scalar domains never
        distribute over a multi-atom group: `year >= (2019 or 2020)` and
        `retracted is (true or false)` are errors, not unions)."""
        self._skip_annot()
        t = self.peek()
        if t is not None and t.kind != "RP":
            raise oql_error("OQL_GROUP_NEEDS_ONE_VALUE", one_value_msg,
                           one_value_fixit, t.pos)
        self._expect_rp()

    def _parse_bool_value(self, fld: Field, negated: bool) -> LeafFilter:
        # A boolean is an ordinary value clause: `<name> is true|false` (oxjob #363,
        # replacing the old `it's …`/`it has …` special form). `is not` folds into the
        # value (`is not true` -> false), so a bool leaf never carries is_negated.
        # A bool has no value LIST to extend (no `is (true or false)`), so clear the
        # value-start marker the sectioned "add another value" menu reads.
        self._last_value_start_i = None
        self._want(CTX_VALUE, kind="bool")
        # canonical parens (#554): `is (true)`; `(not true)` folds like `is not true`.
        grouped = self._open_scalar_group()
        if grouped:
            self._want(CTX_VALUE, kind="bool")
            while self.word_is("not"):
                self.next()
                negated = not negated
                self._skip_annot()
        t = self.peek()
        if t is None or t.kind != "WORD" or t.val.lower() not in ("true", "false"):
            raise oql_error("OQL_BAD_BOOL_VALUE",
                           f'"{fld.oql}" is a yes/no property — its value must be '
                           f'true or false',
                           f'e.g. {fld.oql} is (true)', t.pos if t else None)
        val = (t.val.lower() == "true")
        self.next()
        if negated:
            val = not val
        self._skip_annot()
        if grouped:
            self._close_scalar_group(
                f'"{fld.oql}" is a yes/no property — it takes exactly one value',
                f'{fld.oql} is (true) or {fld.oql} is (false), never both in '
                f'one group')
        if self._continues_value():
            t2 = self.peek()
            raise oql_error("OQL_UNDELIMITED_TERM_LIST",
                           f'"{fld.oql}" got more than one value',
                           f'a yes/no property takes one value: {fld.oql} is (true)',
                           t2.pos if t2 else None)
        return LeafFilter(fld.column, val, "is")

    def _parse_value_clause(self, field: str, fld: Field, op: str) -> FilterType:
        # Record where this clause's value begins (token index) so the post-connective
        # sectioned menu can frame the existing value(s) for the auto-paren rewrite
        # (oxjob #357). Bookkeeping only — read in context mode.
        self._last_value_start_i = self.i
        # (no _skip_annot here — _parse_scalar must SEE a lone annotation so it
        # can raise OQL_MISSING_ENTITY_ID for "institution is [Harvard]".)
        # collection membership: is [not] in collection (col_…) (oxjob #363; #554
        # canonical parens)
        if op in ("incoll", "nincoll"):
            negated = (op == "nincoll")
            # bare `not` prefix on the value (decision 23): canonical is
            # `work is in collection (not col_x)`; `is not in collection` is the
            # accepted input alias (op == "nincoll"). Both land on is_negated.
            if self.word_is("not"):
                self.next()
                self._skip_annot()
                negated = not negated
            grouped = self._open_scalar_group()
            if grouped:
                while self.word_is("not"):     # (not col_x) — not inside the group
                    self.next()
                    negated = not negated
                    self._skip_annot()
            v = self._parse_scalar(fld)
            if grouped:
                self._close_scalar_group(
                    'one collection per clause',
                    'e.g. work is in collection (col_abc123); union several '
                    'with or-clauses')
            if not (isinstance(v, str) and v.startswith("col_")):
                raise oql_error("OQL_BAD_COLLECTION_REF",
                               f'"is in collection" needs a collection id (col_…), got "{v}"',
                               'e.g. work is in collection (col_abc123)')
            return LeafFilter(fld.column, v, "in collection",
                              is_negated=negated)
        # comparison — a single scalar, canonically parenthesized (D5; #554)
        if op in (">", ">=", "<", "<="):
            grouped = self._open_scalar_group()
            v = self._parse_scalar(fld)
            if grouped:
                self._close_scalar_group(
                    'a comparison takes exactly one bound',
                    f'e.g. {field} {op} ({v})')
            # date axis fields route inclusive bounds to the from_*/to_* params
            # (the only inclusive form at ES); strict >/< stay on the base column.
            # (oxjob #407 — see the `date` kind notes in the Field dataclass.)
            if fld.kind == "date":
                if op == ">=" and fld.date_from_col:
                    return LeafFilter(fld.date_from_col, v, "is")
                if op == "<=" and fld.date_to_col:
                    return LeafFilter(fld.date_to_col, v, "is")
                # strict >/< (or a bound column given a comparison) -> base column
                return LeafFilter(fld.column, v, op)
            return LeafFilter(fld.column, v, op)
        # is / is not
        negated = (op == "isnot")
        # boolean flag: `<name> is true|false` (oxjob #363)
        if fld.kind == "bool":
            return self._parse_bool_value(fld, negated)
        # a parenthesized boolean group of values: `country is (us or uk)`,
        # `country is not (us or uk)` (the base operator negates the whole group).
        # implicit_and=False (#554): `type is (article review)` is a loud error,
        # never a silent AND.
        grp = self._parse_grouped_operand(lambda: self._parse_value_operand(fld),
                                          implicit_and=False)
        if grp is not None:
            return _negate(grp) if negated else grp
        # unknown / null
        if self.word_is("unknown", "null"):
            self.next()
            return LeafFilter(fld.column, None, "is", is_negated=negated)
        # the dash range literal (`year is 2019-2023` / `2019-` / `-2023`) was
        # REMOVED — charter decision 24. Reject it with a targeted fix-it pointing
        # at the explicit endpoint form, rather than letting it fall through to a
        # generic "not a number". The URL range form + OQO bounds are unaffected;
        # only the OQL literal goes away (a URL range still renders endpoints).
        if fld.kind == "num":
            t = self.peek()
            ends = (_range_endpoints(t.val)
                    if t is not None and t.kind == "WORD" and "-" in t.val else None)
            if ends is not None:
                raise oql_error("OQL_RANGE_LITERAL_REMOVED",
                               f'numeric ranges like "{t.val}" were removed; '
                               "write explicit endpoint clauses",
                               f"e.g. {_range_endpoint_fixit(field, *ends)}", t.pos)
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
        a nested `(...)` group, the null sentinel `unknown`/`null`, or one scalar
        value (-> an `is` leaf)."""
        t = self.peek()
        if t is not None and t.kind == "WORD" and t.val.lower() == "not":
            self._consume_not(t)  # bare prefix `not` (decision 23)
            return _negate(self._parse_value_operand(fld))
        grp = self._parse_grouped_operand(lambda: self._parse_value_operand(fld),
                                          implicit_and=False)
        if grp is not None:
            return grp
        if t is not None and t.kind == "COMMA":
            raise oql_error("OQL_COMMA_IN_GROUP",
                           "items in a (…) group are separated by 'or'/'and', "
                           "not commas",
                           "replace the comma with 'or' (or 'and')", t.pos)
        # `unknown` / `null` inside a value group is the null sentinel, same as
        # the top-level `is unknown` (#554 — it previously fell through to
        # `_parse_scalar` and misparsed as a literal string). This makes mixed
        # groups expressible: `language is (en or unknown)`. A literal value
        # spelled "unknown" stays reachable via quotes (the canonical render
        # quotes it — see `_value_needs_quote`).
        if self.word_is("unknown", "null"):
            self.next()
            return LeafFilter(fld.column, None, "is")
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
        if t.kind == "WORD" and t.val.lower() in ("group", "sample"):
            return False
        if t.kind == "WORD" and t.val.lower() in _CONNECTIVES:
            # Editor context: a connective with NOTHING after it (cursor sits right
            # after `... or`/`and`) is ambiguous between an undelimited value list
            # and the start of a new clause. Don't fail-fast — treat the value as
            # complete so `_parse_expr` consumes the connective and the next operand
            # records the (post-connective) FIELD context for the sectioned menu
            # (oxjob #357). Strict parsing is untouched (guarded on `_ctx_mode`).
            if self._ctx_mode and self.peek(1) is None:
                return False
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
                               'put the OpenAlex ID first, e.g. institution is (I136199984 [Harvard])',
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
        if fld.kind == "date":
            return _coerce_date(val, fld, t.pos)
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
        # canonical parens (#554): `is similar to ("...")`; bare `"..."` accepted.
        grouped = self._open_scalar_group()
        if grouped:
            self._want(CTX_VALUE, fld=fld, kind="search")
        t = self.peek()
        if t is None or t.kind != "STRING":
            raise oql_error("OQL_SEMANTIC_NEEDS_TEXT",
                           '"is similar to" needs a quoted text passage',
                           'e.g. abstract is similar to ("...")',
                           t.pos if t else None)
        self.next()
        if grouped:
            self._close_scalar_group(
                '"is similar to" takes exactly one quoted passage',
                'e.g. abstract is similar to ("...")')
        return LeafFilter(fld.column + ".search.semantic", t.val, "has")

    def _parse_search_value(self, base: str) -> FilterType:
        """Top-level value after `has`: a single bare atom, or a `(...)`
        boolean group. 2+ bare atoms (`title has foo bar`, `... foo or bar`)
        are a loud OQL_UNDELIMITED_TERM_LIST (D1) — that's the rule that kills the
        silent-keyword-truncation footgun, since a reserved word can only float
        when there are 2+ unparenthesized terms."""
        self._skip_annot()
        self._want(CTX_VALUE, fld=self._cur_fld, kind="search")
        t = self.peek()
        if t is not None and t.kind == "WORD" and t.val.lower() == "not":
            # Bare prefix `not` negates the next search operand (decision 23):
            # `title has not dog` -> one negated leaf, rendered
            # `title has not dog`. A multi-word run is one value-node, so
            # `not machine learning` negates the whole run.
            return self._parse_search_operand(base)
        # leading list proximity `within N (a, b, ...)` (oxjob #514) — the ONE proximity
        # surface; intercept before the value group so the trailing `(...)` is read as the
        # operand list, not a boolean group.
        if self.word_is("within"):
            return self._parse_proximity_list(base)
        # a `(...)` boolean group — `_parse_grouped_operand` consumes it.
        grp = self._parse_grouped_operand(lambda: self._parse_search_operand(base))
        if grp is not None:
            return grp
        leaf = self._parse_search_atom(base)
        self._skip_annot()
        if self._continues_value():
            t2 = self.peek()
            raise oql_error("OQL_UNDELIMITED_TERM_LIST",
                           "two or more search terms with no parentheses "
                           "(a reserved word could be silently swallowed)",
                           'wrap the terms, e.g. has (a or b), or quote a '
                           'phrase, e.g. has "a b"', t2.pos if t2 else None)
        return leaf

    def _parse_grouped_operand(self, parse_operand,
                               implicit_and=True) -> Optional[FilterType]:
        """If the cursor is at a bare `(` group opener, parse the whole group
        (consuming its `)`) and return its filter; else return None without
        consuming. The group is `or`/`and`-separated (the existing
        `_parse_bool_expr` machinery); groups nest freely via `parse_operand`.
        `implicit_and=False` (the `is (...)` value side, #554) makes bare
        space-adjacency between operands a loud error instead of a silent AND."""
        t = self.peek()
        if t is None or t.kind != "LP":
            return None
        self.next()                       # (
        e = self._parse_bool_expr(parse_operand, implicit_and=implicit_and)
        self._expect_rp()
        return e

    def _parse_bool_expr(self, parse_operand, implicit_and=True) -> FilterType:
        """A boolean group body inside `(...)`: explicit-connective-separated
        *runs* of space-adjacent operands (implicit AND). Mixing a space-run or an
        explicit `and` with an explicit `or` at one level is resolved by the
        standard precedence AND > OR (not an error) — each implicit/explicit AND
        run becomes one OR-operand. `parse_operand` reads one operand (search term
        or value, per the caller). Shared by the search side (`has (...)`) and the
        value side (`is (...)`) so they can't drift — but the value side passes
        `implicit_and=False`: between VALUES a bare space is never a silent join
        (#554; a user who pastes `type is (article review)` almost certainly means
        `or`, and implicit AND gave a silent count-0). The `has` side keeps its
        run-merge (D2 reversal, #363) — a bare-word run there is ONE stemmed node
        consumed by `_parse_search_atom` before this machinery sees a second
        operand, so `implicit_and` only bites mixed-operand adjacency."""
        outer = self._in_list
        self._in_list = True
        try:
            unit, n = self._parse_bool_run(parse_operand, implicit_and=implicit_and)
            units = [unit]
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
                    unit, n = self._parse_bool_run(parse_operand,
                                                   implicit_and=implicit_and)
                    units.append(unit)
                    continue
                break
            # AND > OR precedence over the (implicit-AND-grouped) units. A space-run
            # is already one AND-unit; the helper groups explicit `and`-joined units
            # too, then ORs across — never silently flat, never an error.
            return _precedence_tree(units, conns)
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

    def _parse_bool_run(self, parse_operand,
                        implicit_and=True) -> Tuple[FilterType, int]:
        """One or more space-adjacent operands = implicit AND (one AND-precedence
        unit). Returns (filter, n_operands); the caller treats the unit as a single
        operand when building the AND > OR precedence tree.

        With `implicit_and=False` (the `is (...)` value side, #554) a second
        space-adjacent operand is a LOUD error — between values the join must be
        explicit ("did you mean or?"). In recover mode the error is collected and
        parsing continues (so the editor squiggles every gap); in editor-context
        mode we stay lenient so completion still works mid-typing."""
        atoms = [self._group_operand(parse_operand)]
        while True:
            self._skip_annot()
            t = self.peek()
            if t is None or t.kind in ("RP", "SEMI", "COMMA"):
                break
            if t.kind == "WORD" and t.val.lower() in _CONNECTIVES:
                break  # explicit connective -> handled by _parse_bool_expr
            if t.kind == "WORD" and t.val.lower() in ("group", "sample"):
                break
            if not implicit_and and not self._ctx_mode:
                err = oql_error("OQL_GROUP_VALUES_NEED_CONNECTIVE",
                               f'two values with no connective between them '
                               f'(before "{t.val}")',
                               "add 'or' between the values (or 'and' if you "
                               "mean both)", t.pos)
                if self._recover_mode:
                    self._diagnostics.append(err)
                else:
                    raise err
            atoms.append(self._group_operand(parse_operand))  # implicit AND
        if len(atoms) == 1:
            return atoms[0], 1
        return BranchFilter(join="and", filters=atoms), len(atoms)

    def _starts_new_clause(self, k: int) -> bool:
        """After a connective at offset k, do the tokens begin a new field clause?
        (a known field/boolean phrase followed by an operator)."""
        return self._clause_lookahead(k, require_known_field=True)

    def _looks_like_new_clause(self, k: int) -> bool:
        """Like `_starts_new_clause`, but does NOT require the field to be a known
        alias — any word (or `it's …`) followed within a few tokens by an operator
        looks like a new clause (a bare `(` counts too). Used by the arity guard
        (`_continues_value`) so a misspelled/unknown next field (`year is 2020 and
        bogus is 5`) is treated as a new (bad) clause to report, not as a second
        undelimited value."""
        return self._clause_lookahead(k, require_known_field=False)

    def _clause_lookahead(self, k: int, require_known_field: bool) -> bool:
        """Shared body of the two clause-boundary probes above."""
        save = self.i
        self.i += k
        self._skip_annot()
        try:
            t = self.peek()
            # a `(` opens a clause-group (only the relaxed probe accepts this)
            if not require_known_field and t and t.kind == "LP":
                return True
            # a COMPLETE row-subject verb phrase followed by `(` (`it cites (…`)
            # opens a clause (oxjob #557); an incomplete one (`… and it`) does
            # not — inside a bare search run, a lone `it` stays an ordinary
            # search term. The `(` requirement keeps prose like `… and it cites
            # wonder` a loud D1 undelimited-run error instead of silently
            # manufacturing a garbage id filter.
            mrs = match_row_subject(self.toks, self.i)
            if mrs is not None and mrs[2]:
                after = self.peek(mrs[1])
                if after is not None and after.kind == "LP":
                    return True
            # a (known, when required) field word-run followed by an operator
            parts = []
            for j in range(0, 4):
                tt = self.peek(j)
                if not tt or tt.kind != "WORD":
                    break
                parts.append(tt.val)
                if require_known_field and " ".join(parts).lower() not in _ALIAS:
                    continue
                after = self.peek(j + 1)
                if after and (after.kind == "OP" or
                              (after.kind == "WORD" and after.val.lower() in
                               ("is", "has", "does", "doesn't", "doesnt"))):
                    return True
            return False
        finally:
            self.i = save

    def _parse_search_operand(self, base: str) -> FilterType:
        """One operand inside a `has (...)` group: a `not`-prefixed operand, a nested
        `(...)` group, or one search atom."""
        self._skip_annot()
        # an empty search-term slot at the cursor (`title has |`)
        self._want(CTX_VALUE, fld=self._cur_fld, kind="search")
        t = self.peek()
        if t is None:
            raise oql_error("OQL_MISSING_VALUE", "expected a search term", "")
        if t.kind == "BANG":
            # a leading `!` (the WoS within-value NOT) — not an OQL operator (#432)
            raise oql_error("OQL_BANG_NOT_SUPPORTED", position=t.pos)
        if t.kind == "WORD" and t.val.lower() == "not":
            self._consume_not(t)  # bare prefix `not` (decision 23)
            return _negate(self._parse_search_operand(base))
        # leading list proximity `within N (a, b, ...)` nested in a group (oxjob #514).
        if self.word_is("within"):
            return self._parse_proximity_list(base)
        # a `(...)` boolean group — `_parse_grouped_operand` consumes it.
        grp = self._parse_grouped_operand(lambda: self._parse_search_operand(base))
        if grp is not None:
            return grp
        operand = self._parse_search_atom(base, in_group=True)
        # `!` (the WoS / classic-OXURL within-value NOT, e.g. `England!"New England"`)
        # is NOT an OQL operator — OQL negates with not(…). It is lexed as a BANG
        # token only so we can reject it loudly with a fix-it, instead of silently
        # folding it into the stemmed value (the #432 mis-parse). The compact
        # `term!"phrase"` form lives only on the classic OXURL surface (#431).
        if self.peek() is not None and self.peek().kind == "BANG":
            raise oql_error("OQL_BANG_NOT_SUPPORTED", position=self.peek().pos)
        return operand

    def _parse_proximity_list(self, base: str) -> LeafFilter:
        """Leading list proximity `within N (op, op, ...)` — the ONE OQL proximity
        surface (oxjob #514).

        K operands (2+) that must appear within an N-word window of each other,
        unordered. Quotes FREEZE an operand into an adjacent phrase; listing operands
        separately lets them move relative to each other. Stemming is per-leaf: all
        operands bare => stemmed (`.search`); all quoted => exact (`.search.exact`);
        mixing is rejected (one leaf, one column). Encodes to the canonical `~`-string
        `"op1"~N~"op2"~...`, which the engine compiles to an ES `intervals` `all_of`
        query (binary K=2 reuses the #355 binary path byte-for-byte; K>=3 the #514 list
        path). The OXURL `~` surface is untouched — it still only parses single/binary.
        """
        wt = self.peek()                       # `within`
        self.next()
        nt = self.peek()
        if not nt or nt.kind != "WORD" or not nt.val.isdigit():
            raise oql_error("OQL_BAD_PROXIMITY", 'expected a number after "within"',
                           'e.g. within 3 ("smart", "phone")', nt.pos if nt else wt.pos)
        n = int(nt.val)
        self.next()
        lp = self.peek()
        if not lp or lp.kind != "LP":
            raise oql_error("OQL_BAD_PROXIMITY",
                           'proximity needs a parenthesized operand list',
                           'e.g. within 3 ("smart", "phone")', lp.pos if lp else wt.pos)
        self.next()                            # (
        operands: List[Tuple[str, bool]] = []  # (text, quoted)
        while True:
            self._skip_annot()
            ot = self.peek()
            if ot is None:
                raise oql_error("OQL_BAD_PROXIMITY",
                               'unterminated proximity list — expected ")"',
                               'e.g. within 3 ("smart", "phone")', wt.pos)
            if ot.kind == "RP":
                break
            if ot.kind == "STRING":
                operands.append((ot.val, True))
                self.next()
            elif ot.kind == "WORD" and not self._is_run_break_word(ot.val):
                operands.append((ot.val, False))
                self.next()
            else:
                raise oql_error("OQL_BAD_PROXIMITY",
                               f'unexpected "{ot.val}" in a proximity operand list',
                               'list bare words or quoted phrases, '
                               'e.g. within 3 ("smart", "phone")', ot.pos)
            self._skip_annot()
            sep = self.peek()
            if sep is not None and sep.kind == "COMMA":
                self.next()
                continue
            if sep is not None and sep.kind == "RP":
                continue                        # loop breaks on the RP next pass
            raise oql_error("OQL_BAD_PROXIMITY",
                           'proximity operands must be separated by commas',
                           'e.g. within 3 ("smart", "phone")', sep.pos if sep else wt.pos)
        self.next()                            # )
        if len(operands) < 2:
            raise oql_error("OQL_PROXIMITY_NEEDS_OPERANDS",
                           'proximity needs at least two operands',
                           'e.g. within 3 ("smart", "phone")', wt.pos)
        if len({q for _, q in operands}) > 1:
            raise oql_error("OQL_PROXIMITY_MIXED_OPERANDS",
                           'proximity operands must be all bare (stemmed) or all quoted '
                           '(exact), not a mix',
                           'quote every operand or none, e.g. within 3 ("smart", "phone")',
                           wt.pos)
        quoted = operands[0][1]
        col = base + (".search.exact" if quoted else ".search")
        # Wildcards: a bare (stemmed) operand can't carry one (#364 — stemming strips the
        # literal prefix); a quoted operand can, validated per-token + a shared expansion
        # budget across the whole intervals query (#355 guard).
        all_tokens = [w for text, _ in operands for w in text.split()]
        has_wild = any("*" in w or "?" in w for w in all_tokens)
        if has_wild and not quoted:
            bad = next(w for w in all_tokens if "*" in w or "?" in w)
            raise oql_error("OQL_WILDCARD_NEEDS_EXACT",
                           f'wildcards run on exact (no-stem) text: {bad}',
                           f'quote the operand: "{bad}"', wt.pos)
        if has_wild:
            for w in all_tokens:
                _validate_wildcards(w, wt.pos)
            _validate_wildcard_budget(all_tokens, wt.pos)
        # Canonical `~`-string: `"op1"~N~"op2"~"op3"~...` (binary K=2 is `"op1"~N~"op2"`,
        # byte-identical to the #355 form). Operands are always quoted in the value (the
        # quotes are structural delimiters); the COLUMN carries stem-vs-exact.
        parts = [f'"{operands[0][0]}"', f"~{n}~", f'"{operands[1][0]}"']
        parts += [f'~"{text}"' for text, _ in operands[2:]]
        return LeafFilter(col, "".join(parts), "has")

    def _is_run_break_word(self, val: str) -> bool:
        """A bare word that TERMINATES a multi-word search run (#1) rather than
        folding into its stemmed value: a boolean connective, `not`, or a
        search/directive keyword the grammar handles after the run."""
        return val.lower() in _SEARCH_RUN_RESERVED

    def _parse_search_atom(self, base: str, in_group: bool = False) -> LeafFilter:
        # Stemming is ON by default; quotes turn it OFF (exact). `stemmed "phrase"`
        # is the bridge: an adjacent phrase that STAYS stemmed (recall).
        #   bare term          -> stemmed          (.search)
        #   "phrase"           -> exact, adjacent  (.search.exact)
        #   stemmed "phrase"   -> stemmed, adjacent (.search)
        self._skip_annot()
        stemmed_phrase = False
        if self.word_is("stemmed") and self.peek(1) and self.peek(1).kind == "STRING":
            self.next()
            stemmed_phrase = True
        t = self.peek()
        if t is None or t.kind not in ("WORD", "STRING"):
            raise oql_error("OQL_MISSING_VALUE", "expected a search term",
                           "", t.pos if t else None)
        if t.kind == "STRING":
            text = t.val
            self.next()
            # A wildcard inside quotes is accepted: a quoted phrase is exact (no-stem),
            # which is where wildcards belong (#364 reversed #337's old
            # OQL_WILDCARD_IN_QUOTES reject). A single quoted word (`"bar*"`) routes to
            # the `.search.exact` column and renders bare (corpus #19 -- mirrors the raw
            # API, where strip_singleton_wildcard_quotes unwraps it, zd#9063); a
            # multi-word phrase compiles to an ES `intervals` query (oxjob #355). The
            # blocks below validate each token's shape and pick the column.
            phrase = True
        else:
            # #1 (D2 reversal, oxjob #363): inside a `has (...)` group a
            # maximal run of space-adjacent bare words is ONE stemmed value node
            # (the engine adjacency-boosts the whole run), NOT per-word AND leaves.
            # An embedded *quoted* token is an escape — a literal word that stays
            # stemmed — so a reserved word can live inside a stemmed value:
            # `road traffic safety "and" Ghana` -> one node "road traffic safety
            # and Ghana". Explicit and/or/not (read by _parse_bool_expr) still
            # build the boolean tree between such nodes. At the top level (no
            # parens) we do NOT merge — the D1 arity rule still requires 2+ terms
            # to be parenthesized (the canonical render always parenthesizes).
            _validate_wildcards(t.val, t.pos)
            words = [t.val]
            self.next()
            if in_group:
                while True:
                    nt = self.peek()
                    if nt is None:
                        break
                    # a `(` mid-run starts a nested group, not more stemmed words —
                    # break the run so `has (machine learning (a or b))` reads the
                    # run then the group.
                    if nt.kind == "LP":
                        break
                    if nt.kind == "WORD" and not self._is_run_break_word(nt.val):
                        _validate_wildcards(nt.val, nt.pos)
                        words.append(nt.val)
                        self.next()
                        continue
                    if nt.kind == "STRING":  # quoted escape -> literal stemmed word(s)
                        words.append(nt.val)
                        self.next()
                        continue
                    break
            text = " ".join(words)
            phrase = False
        # quoted => exact (.exact column) unless `stemmed` keeps it stemmed
        stemmed = (not phrase) or stemmed_phrase
        col = base + (".search" if stemmed else ".search.exact")
        has_wildcard = "*" in text or "?" in text
        self._skip_annot()
        # `within` is now ONLY the leading list operator `within N (a, b, ...)` (oxjob
        # #514), intercepted before the atom in _parse_search_value / _parse_search_operand.
        # A `within` TRAILING an atom is the removed suffix form (`"foo bar" within 3
        # words`, `"a" within 3 words of "b"`) — reject loudly with a pointer to the new
        # surface. (The OXURL `~` notation is unaffected; this is the OQL surface only.)
        if self.word_is("within"):
            raise oql_error("OQL_PROXIMITY_SUFFIX_REMOVED",
                           'proximity is written `within N (a, b, ...)` BEFORE the terms, '
                           'not after them',
                           'e.g. within 3 ("smart", "phone")',
                           self.peek().pos)
        # #364: outside a proximity phrase, a wildcard must run on exact (no-stem)
        # text — stemming at index time removes the literal prefix, so a wildcard
        # on a stemmed field is silently wrong (`studies*` = 2.4k stemmed vs 2.2M
        # no-stem). A bare term and a `stemmed` phrase are stemmed → reject with a
        # quote-it fix-it. A quoted phrase is exact → the sanctioned wildcard path.
        # (This deliberately REVERSES #337's old OQL_WILDCARD_IN_QUOTES guidance:
        # quotes are now where wildcards belong.)
        if has_wildcard and stemmed:
            if stemmed_phrase:
                raise oql_error("OQL_WILDCARD_NEEDS_EXACT",
                               f'wildcards run on exact (no-stem) text, but "stemmed" '
                               f'keeps the phrase stemmed: "{text}"',
                               'drop "stemmed" so the wildcard runs on exact text', t.pos)
            raise oql_error("OQL_WILDCARD_NEEDS_EXACT",
                           f'wildcards run on exact (no-stem) text: {text}',
                           f'quote it: "{text}"', t.pos)
        # A quoted wildcard (`"studies*"`) is exact — validate each token's shape
        # so #337's leading / sub-3-char-prefix rejections still hold inside quotes.
        if phrase and has_wildcard:
            for word in text.split():
                _validate_wildcards(word, t.pos)
            _validate_wildcard_budget(text.split(), t.pos)
        # encode value: a quoted phrase keeps its quotes; a bare single word is bare
        # (the column suffix carries exact-vs-stemmed). EXCEPTION: a quoted single
        # "word" that the analyzer splits into >1 subtoken (a hyphen/slash token like
        # "3xTg-AD" or "APP/PS1") is NOT equivalent to the bare form — on a stemmed
        # .search column quoted = adjacent subtokens (phrase), bare = subtokens AND'd,
        # which return different result sets (measured live: `"3xTg-AD"` 2027 vs
        # `3xTg-AD` 2354; `"APP/PS1"` 6440 vs 8056). So keep the quotes whenever
        # dropping them would change tokenization; a truly atomic single token (cat)
        # still renders bare so the common case stays unquoted. (oxjob #363 case W3.3)
        # The single-token subtoken exception is STEMMED-only: on `.search.exact`
        # the column suffix already carries exactness (and wildcard patterns like
        # "foo*bar" live there — `*`/`?` are metachars, not delimiters), so an exact
        # single token stays bare. On the stemmed `.search` column a quoted
        # hyphen/slash token diverges from bare, so keep its quotes.
        if phrase and (len(text.split()) > 1
                       or (stemmed and len(re.findall(r"\w+", text)) > 1)):
            value = f'"{text}"'
        else:
            value = text
        return LeafFilter(col, value, "has")

    # -- directives --
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


def _precedence_tree(operands: List[FilterType], conns: List[str]) -> FilterType:
    """Combine a flat operand sequence joined by `and`/`or` connectives into a
    tree honoring the standard boolean precedence **AND binds tighter than OR**
    (`not` already binds tightest — it's a prefix operator handled at the operand
    level). `conns[i]` is the connective between `operands[i]` and `operands[i+1]`;
    `len(conns) == len(operands) - 1`.

    This is the same precedence Web of Science, Scopus (since early 2026), boolean
    algebra, and every programming language use — so OQL never throws on a mixed
    `and`/`or` level; it groups it. The canonical render makes the grouping
    explicit with parentheses (a nested AND group inside the top-level OR is
    rendered parenthesized), so the structure is never left to the reader's head.

    A pure-AND or pure-OR sequence collapses to a single flat `BranchFilter`
    (no nesting, no added parens) — identical to the pre-precedence behavior.
    """
    if not conns:
        return operands[0]
    # Split the sequence at every `or`: each maximal `and`-joined run becomes one
    # OR-operand. (Implicit-AND units from a value/search group arrive already
    # grouped as one operand; AND is associative, so treating them as a single
    # AND-precedence operand is equivalent.)
    or_groups: List[List[FilterType]] = [[operands[0]]]
    for conn, operand in zip(conns, operands[1:]):
        if conn == "or":
            or_groups.append([operand])
        else:  # "and"
            or_groups[-1].append(operand)
    and_nodes = [grp[0] if len(grp) == 1 else BranchFilter(join="and", filters=grp)
                 for grp in or_groups]
    if len(and_nodes) == 1:
        return and_nodes[0]
    return BranchFilter(join="or", filters=and_nodes)


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
        raise oql_error("OQL_EMPTY", "empty query", 'e.g. "works where year >= (2020)"')
    p = _Parser(toks)
    oqo = p.parse()
    return oqo


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
                                'e.g. "works where year >= (2020)"')]
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
      .search (stemmed):       bare word | stemmed "phrase" | within N (a, b, ...)
      .search.exact (exact):   "word"    | "phrase"      | within N ("a", "b", ...)
    """
    stemmed = not column.endswith(".search.exact")  # .search (and anything else) stems
    # List / binary proximity `"a"~N~"b"[~"c"...]` -> `within N (a, b, ...)` (oxjob #514;
    # the ONE proximity surface, K operands NEAR each other). Operands render bare on a
    # stemmed column, quoted on an exact column — reconstructing the input quoting. Binary
    # (K=2) is the same value shape the OXURL `~` surface uses; rendering it as the list
    # form is intentional (the old `within N words of` suffix surface is gone).
    lst = re.match(r'^"[^"]*"~(\d+)(?:~"[^"]*")+$', value or "")
    if lst:
        slop = lst.group(1)
        operands = re.findall(r'"([^"]*)"', value)
        items = [op if stemmed else f'"{op}"' for op in operands]
        return f'within {slop} ({", ".join(items)})'
    # Single-phrase slop `"P"~N` is OXURL-only now (the OQL suffix form was removed). It
    # is reachable only from a URL-authored OQO; render the equivalent list form by
    # splitting the phrase into operands. This is intentionally lossy (it re-parses to the
    # binary `~N~` form) — single-phrase slop has no round-tripping OQL surface (#514).
    prox = re.match(r'^"(.+)"~(\d+)$', value or "")
    if prox:
        slop = prox.group(2)
        items = [w if stemmed else f'"{w}"' for w in prox.group(1).split()]
        return f'within {slop} ({", ".join(items)})'
    if value.startswith('"') and value.endswith('"') and len(value) >= 2:  # multi-word phrase
        return f"stemmed {value}" if stemmed else value
    if not stemmed:
        # exact single word/token => quoted (`.search.exact` carries exactness)
        return f'"{value}"'
    # A stemmed value is ONE node (#1 single node, D2 reversal): emit its inner
    # token form, dropping un-reparseable special chars (#3) and quoting embedded
    # reserved words (#2). No parens of its own (#554): the canonical clause
    # always wraps the whole value in `( … )`, and inside a group a bare
    # multi-token run re-parses to this same single stemmed node (the run-merge),
    # so `title has (machine learning)` round-trips with no inner parens.
    return _render_stemmed_search_value(value)


def _value_needs_quote(value: str) -> bool:
    """A bare value atom is one token: it must be quoted if it contains whitespace
    (else `ebook platform` re-parses as the adjacency-AND of two atoms) or collides
    with a grammar keyword / delimiter. (oxjob #363 — first hit by multi-word
    source-type slugs like `ebook platform`, `book series`.)"""
    if not value:
        return False
    return (any(c.isspace() for c in value)
            or value.lower() in _CONNECTIVES
            or value.lower() in ("not", "is", "has", "where", "group",
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

# Annotation for a shape-valid entity ID the resolver couldn't find (oxjob #418).
# Lowercase/neutral so it never reads as an entity literally named that, and never
# implies the query is invalid. Like `[display name]`, it's discarded on re-parse.
_NO_ENTITY_ANNOTATION = "[no entity found]"


def _column_resolves_name(column_id) -> bool:
    """True if this column is name-resolvable in production — i.e. it derives
    an annotation namespace from the registry (`namespace_for_column`, #565).
    A None namespace means the column never shows a name (entity self-ids like
    `ids.openalex`, readable slugs), so a resolver miss there is "no name for
    this kind of column", NOT "entity not found" — those stay bare (oxjob #418)."""
    return namespace_for_column(column_id) is not None


def _resolver_covers(resolver, column_id) -> bool:
    """Whether the render should consult `resolver` for this column's display
    names — and, on a miss, mark the value `[no entity found]` (#418). An
    entity-aware engine resolver (oql_renderer.make_engine_resolver) exposes
    its own coverage as `.covers`, guaranteeing the gate and the lookup can
    never disagree; plain callables (corpus/test lambdas) fall back to the
    entity-blind registry derivation."""
    covers = getattr(resolver, "covers", None)
    if covers is not None:
        return bool(covers(column_id))
    return _column_resolves_name(column_id)


def _truncate_name(name: str) -> str:
    """Clip a display-name annotation to a uniform length with an ellipsis."""
    name = " ".join(name.split())  # collapse internal whitespace/newlines
    if len(name) > _NAME_ANNOTATION_MAX:
        return name[: _NAME_ANNOTATION_MAX - 1].rstrip() + "…"
    return name


def _uniform_search_base(f: FilterType):
    """If every leaf anywhere under `f` is a plain (non-semantic) search leaf on
    the same *base* field, return a representative column_id; else None. The whole
    boolean subtree then factors into one `field has (...)` clause whose
    parens hold the boolean of bare terms (`title has (a or (b and c))`).
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
    `field is (...)` clause. Comparisons and `in collection` leaves are excluded —
    they are exactly-one-atom surfaces. Null leaves (`value: None`) are ordinary
    group members since #554 (`unknown` in a group is the null sentinel), so
    `language is (en or unknown)` factors like any other value group."""
    cols = set()

    def walk(node) -> bool:
        if isinstance(node, LeafFilter):
            if not (node.operator == "is" and not _is_search_leaf(node)):
                return False
            fld = _BY_COLUMN.get(node.column_id)
            if fld and fld.kind in ("date", "bool"):
                return False  # bools/dates are exactly-one-atom surfaces
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
        leaf = render_leaf(f)
        # In-group negation renders as a bare `not ` prefix on the atom (charter
        # decision 23). Canonical OQO is NNF (negation on leaves), so the argument
        # is always one value-node — `not` binds it with no parens to recall.
        if f.is_negated:
            return [_seg("text", "not ")] + leaf
        return leaf
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
    ClauseMeta, GroupMeta, EntityValue, SampleDirective,
    GroupByDirective, GroupByMeta, SampleMeta, ExprNode, stringify,
)


def _seg(kind, text, **meta):
    return Segment(kind=kind, text=text, meta=SegmentMeta(**meta) if meta else None)


def _value_segments(fld, value, column_id, resolver):
    """Segments for one value: the bare value, then ` [name]` when the column
    resolves a display name (truncated to a uniform length with an ellipsis).
    Whether a column resolves names at all derives from the registry
    (`_resolver_covers` -> `namespace_for_column`, #565) — a non-covered column
    (self-id, readable slug, no entity_type) never consults the resolver and
    stays bare."""
    rendered = _render_value(fld, value)
    segs = [_seg("value", rendered, value=value, column_id=column_id)]
    entity = None
    # fld None = an uncurated column rendering its raw column_id — it can still
    # be covered (registry entity_type), e.g. `authorships.institutions.id`;
    # pre-#565 those always rendered bare because the hand maps missed them.
    if (resolver and (fld is None or fld.kind not in ("search", "collection"))
            and isinstance(value, str) and not value.startswith("col_")
            and _resolver_covers(resolver, column_id)):
        name = _call_resolver(resolver, value, column_id)
        if name:
            shown = _truncate_name(name)
            segs.append(_seg("text", " "))
            segs.append(_seg("id", f"[{shown}]", entity_display_name=shown,
                             entity_display_id=f"[{shown}]"))
            entity = EntityValue(id=value, short_id=value, display_name=name)
        else:
            # Resolver consulted, no match → a shape-valid ID that doesn't exist
            # (deleted / merged-not-followed / typo). Mark it so a reader can't
            # confuse it with the resolverless case (no resolver → bare ID,
            # nothing was looked up). Display-only; the `[...]` annotation is
            # discarded on re-parse. Only covered columns reach here — a miss
            # on a self-id column means "no name for this kind of column", not
            # "entity not found", so those stay bare. (oxjob #418)
            segs.append(_seg("text", " "))
            segs.append(_seg("id", _NO_ENTITY_ANNOTATION))
    return segs, entity


def _leaf_node(f: LeafFilter, resolver=None) -> ClauseNode:
    # #554: a condition's value is ALWAYS a parenthesized group in canonical
    # OQL — every leaf clause below wraps its value in `( … )` (bare singletons
    # remain accepted on input). Standalone negation moves INSIDE the group
    # (`country is (not FR)`), uniform with the merged case (`(not FR and US)`).
    if _is_search_leaf(f):
        name, mode = _oql_field(f.column_id)
        if mode == "semantic":
            v = (f.value or "").strip('"')
            segs = [_seg("column", name, column_id=f.column_id),
                    _seg("operator", " is similar to "), _seg("text", "("),
                    _seg("value", f'"{v}"', value=f.value), _seg("text", ")")]
        else:
            # decision 23: negation is a bare `not ` prefix on the value, never a
            # `does not have` predicate (`title has (not pediatric)`).
            term = _render_term(f.value, f.column_id)
            val = f"not {term}" if f.is_negated else term
            segs = [_seg("column", name, column_id=f.column_id),
                    _seg("operator", " has "), _seg("text", "("),
                    _seg("value", val, value=f.value), _seg("text", ")")]
        return ClauseNode(segments=segs, clause_kind="text", meta=ClauseMeta(
            column_id=f.column_id, operator=f.operator or "has",
            value=f.value, column_display_name=name))

    fld = _BY_COLUMN.get(f.column_id)
    name = fld.oql if fld else f.column_id
    # date bound columns (from_*/to_*) render via the axis word + comparison op
    # (oxjob #407). The leaf carries op="is" on the bound column; we print
    # `<axis> >= <date>` / `<axis> <= <date>` (the inverse of the parse routing).
    if fld and fld.kind == "date" and fld.date_bound and f.value is not None:
        segs = [_seg("column", fld.date_axis, column_id=f.column_id),
                _seg("operator", f" {fld.date_bound} "), _seg("text", "("),
                _seg("value", _render_value(fld, f.value), value=f.value),
                _seg("text", ")")]
        return ClauseNode(segments=segs, clause_kind="comparison", meta=ClauseMeta(
            column_id=f.column_id, operator=fld.date_bound, value=f.value,
            column_display_name=fld.date_axis))
    # boolean flag: a plain `<name> is (true|false)` clause (oxjob #363). Negation
    # folds into the value (`is not true` -> false), so the canonical form is always
    # `is (true)` / `is (false)` — never a separate `not`.
    if fld and fld.kind == "bool" and isinstance(f.value, bool):
        effective = f.value != f.is_negated  # XOR: fold any is_negated into the value
        segs = [_seg("column", name, column_id=f.column_id),
                _seg("operator", " is "), _seg("text", "("),
                _seg("value", "true" if effective else "false", value=effective),
                _seg("text", ")")]
        return ClauseNode(segments=segs, clause_kind="boolean", meta=ClauseMeta(
            column_id=f.column_id, operator="is", value=effective,
            column_display_name=name))
    # row-subject verb-phrase leaf (oxjob #557): `it cites (…)` / `it's cited by
    # (…)` / `it's related to (…)`. The subject seg carries the column_id; the
    # verb phrase is the operator slot; negation and `unknown` sit inside the
    # value group like every other leaf. column_display_name is the BARE verb
    # ("cites"/"cited by"/"related to") — the GUI-chip label.
    rs = _ROW_SUBJECT_RENDER.get(f.column_id)
    if rs is not None and f.operator == "is":
        subj, verb, bare = rs
        entity = None
        if f.value is None:
            val_segs = [_seg("value", "not unknown" if f.is_negated else "unknown",
                             value=None)]
            kind = "null"
        else:
            val_segs, entity = _value_segments(fld, f.value, f.column_id, resolver)
            if f.is_negated:
                val_segs = [_seg("text", "not ")] + val_segs
            kind = "entity"
        segs = ([_seg("column", subj, column_id=f.column_id),
                 _seg("operator", verb), _seg("text", "(")]
                + val_segs + [_seg("text", ")")])
        return ClauseNode(segments=segs, clause_kind=kind, meta=ClauseMeta(
            column_id=f.column_id, operator="is", value=f.value,
            column_display_name=bare, value_entity=entity))
    if f.value is None:
        # `language is (unknown)` / negated `language is (not unknown)` — the
        # `not` sits inside the group like every other value negation (#554).
        val = "not unknown" if f.is_negated else "unknown"
        segs = [_seg("column", name, column_id=f.column_id),
                _seg("operator", " is "), _seg("text", "("),
                _seg("value", val, value=None), _seg("text", ")")]
        return ClauseNode(segments=segs, clause_kind="null", meta=ClauseMeta(
            column_id=f.column_id, operator="is", value=None,
            column_display_name=name))
    if f.operator in (">", ">=", "<", "<="):
        segs = [_seg("column", name, column_id=f.column_id),
                _seg("operator", f" {f.operator} "), _seg("text", "("),
                _seg("value", _render_value(fld, f.value), value=f.value),
                _seg("text", ")")]
        return ClauseNode(segments=segs, clause_kind="comparison", meta=ClauseMeta(
            column_id=f.column_id, operator=f.operator, value=f.value,
            column_display_name=name))
    if f.operator == "in collection":  # oxjob #363; col_… value, never name-resolved
        # decision 23: negation is a bare `not ` prefix on the value
        # (`work is in collection (not col_x)`), never an `is not in collection`
        # predicate.
        col_val = _render_value(fld, f.value)
        if f.is_negated:
            col_val = f"not {col_val}"
        segs = [_seg("column", name, column_id=f.column_id),
                _seg("operator", " is in collection "), _seg("text", "("),
                _seg("value", col_val, value=f.value), _seg("text", ")")]
        return ClauseNode(segments=segs, clause_kind="collection", meta=ClauseMeta(
            column_id=f.column_id, operator="in collection", value=f.value,
            column_display_name=name))
    # `is` / negated `is`: negation renders INSIDE the value group (#554) —
    # `country is (not FR)` — uniform with the merged case `(not FR and US)`.
    # `is not …` stays accepted input only; it never survives canonicalization.
    val_segs, entity = _value_segments(fld, f.value, f.column_id, resolver)
    if f.is_negated:
        val_segs = [_seg("text", "not ")] + val_segs
    segs = ([_seg("column", name, column_id=f.column_id),
             _seg("operator", " is "), _seg("text", "(")]
            + val_segs + [_seg("text", ")")])
    kind = "entity" if (fld and fld.kind == "id") else "other"
    return ClauseNode(segments=segs, clause_kind=kind, meta=ClauseMeta(
        column_id=f.column_id, operator="is", value=f.value,
        column_display_name=name, value_entity=entity))


def _filter_node(f: FilterType, top=False, resolver=None) -> ExprNode:
    if isinstance(f, LeafFilter):
        return _leaf_node(f, resolver)
    # BranchFilter. A negated branch is non-canonical (NNF pushes negation to
    # the leaves) and should not survive canonicalization; if one reaches here
    # we render it as a bare `not ` prefix on the group so it still re-parses
    # (decision 23) — `not (a or b)`, which the canonicalizer would distribute.
    if f.is_negated:
        inner = _filter_node(BranchFilter(f.join, f.filters), top=False, resolver=resolver)
        return GroupNode(join=f.join, children=[inner], prefix="not ", suffix="",
                         joiner="", meta=GroupMeta(implicit=False))
    # factor a single-base-field search subtree -> `field has (a or b)`
    scol = _uniform_search_base(f)
    if scol is not None:
        name, _ = _oql_field(scol)
        inner = _factored_segments(
            f, lambda lf: [_seg("value", _render_term(lf.value, lf.column_id),
                                value=lf.value)])
        segs = ([_seg("column", name, column_id=scol),
                 _seg("operator", " has "), _seg("text", "(")]
                + inner + [_seg("text", ")")])
        return ClauseNode(segments=segs, clause_kind="text", meta=ClauseMeta(
            column_id=scol, operator="has", value=None,
            column_display_name=name))
    # factor a single-column equality subtree -> `field is (a or b)` — or the
    # row-subject verb form `it cites (a or b)` for relation columns (#557).
    ecol = _uniform_eq_column(f)
    if ecol is not None:
        fld = _BY_COLUMN.get(ecol)
        inner = _factored_segments(
            f, lambda lf: _value_segments(fld, lf.value, lf.column_id, resolver)[0])
        rs = _ROW_SUBJECT_RENDER.get(ecol)
        if rs is not None:
            subj, verb, name = rs
            head = [_seg("column", subj, column_id=ecol),
                    _seg("operator", verb), _seg("text", "(")]
        else:
            name = fld.oql if fld else ecol
            head = [_seg("column", name, column_id=ecol),
                    _seg("operator", " is "), _seg("text", "(")]
        segs = head + inner + [_seg("text", ")")]
        kind = "entity" if (fld and fld.kind == "id") else "other"
        return ClauseNode(segments=segs, clause_kind=kind, meta=ClauseMeta(
            column_id=ecol, operator="is", value=None,
            column_display_name=name))
    # cross-field boolean group -> `(clause1 or clause2)` / `(… and …)`
    items = _merge_same_field_items(list(f.filters), f.join)  # decision 20
    children = [_filter_node(c, top=False, resolver=resolver) for c in items]
    if len(children) == 1:
        return children[0]
    joiner = f" {f.join} "
    prefix, suffix = ("", "") if top else ("(", ")")
    return GroupNode(join=f.join, children=children, prefix=prefix, suffix=suffix,
                     joiner=joiner, meta=GroupMeta(implicit=False))


def _merge_key(item):
    """Decision-20 grouping key: items (children of one boolean node) that share
    a key merge into ONE factored clause — `field op (tree)` — instead of
    rendering as separate clauses. A key is the (surface, identity) pair behind
    the two factor paths: ("search", base field name) for plain search leaves /
    uniform search subtrees (base-name grouping lets stemmed + exact mix, as in
    a native group), or ("eq", column_id) for `is` value leaves / uniform-eq
    subtrees. None = never merges: comparisons (per-leaf operator — bound
    endpoints stay as separate `>=`/`<=` clauses, decision 24), null / collection
    / semantic leaves, bool & date columns (bools render as human phrases, date
    `is` rides the axis surface), and negated branches (canonical OQO is NNF, so
    none should exist)."""
    if isinstance(item, BranchFilter):
        if item.is_negated:
            return None
        scol = _uniform_search_base(item)
        if scol is not None:
            return ("search", _oql_field(scol)[0])
        ecol = _uniform_eq_column(item)
        if ecol is not None and _eq_mergeable(ecol):
            return ("eq", ecol)
        return None
    if not isinstance(item, LeafFilter):
        return None  # defensive: only leaves/branches reach here
    if _is_search_leaf(item):
        name, mode = _oql_field(item.column_id)
        if mode == "semantic":
            return None
        return ("search", name)
    if item.operator == "is" and _eq_mergeable(item.column_id):
        # includes null leaves (value None) — `unknown` is an ordinary group
        # member since #554, so `language is (en or unknown)` merges/factors.
        return ("eq", item.column_id)
    return None


def _eq_mergeable(column_id) -> bool:
    fld = _BY_COLUMN.get(column_id)
    return not (fld and fld.kind in ("date", "bool"))


def _merge_same_field_items(items, join):
    """Charter decision 20 (the SR branch/leaf "One Right Way", #432): among the
    children of one boolean node — including the implicit top-level AND of
    `filter_rows` — the items sharing a `_merge_key` merge into ONE synthetic
    uniform branch, which the factor paths render as a single `field op (tree)`
    clause with the boolean structure (and any leaf `not`s) inside the value
    group. So `title has (A) and title has (B)` re-merges to
    `title has ((A) and (B))`, and `cat ∧ ¬dog` on one field renders
    `title has (not dog and cat)` instead of two clauses. Order is
    preserved (the canonicalizer's deterministic sort — negated-first, then
    value — already puts same-key items adjacent and makes the render
    idempotent); a singleton key keeps its current render — a standalone
    negated leaf renders bare-prefix too (`title has not dog`, decision 23).
    Same-join members are flattened into the synthetic branch (the canonical
    flat form; also keeps re-parse → re-render byte-stable)."""
    groups = {}
    for i, item in enumerate(items):
        key = _merge_key(item)
        if key is not None:
            groups.setdefault(key, []).append(i)
    merged_at, consumed = {}, set()
    for key, idxs in groups.items():
        if len(idxs) < 2:
            continue
        members = []
        for i in idxs:
            m = items[i]
            if isinstance(m, BranchFilter) and m.join == join and not m.is_negated:
                members.extend(m.filters)
            else:
                members.append(m)
        merged_at[idxs[0]] = BranchFilter(join, members)
        consumed.update(idxs[1:])
    if not merged_at:
        return items
    out = []
    for i, item in enumerate(items):
        if i in merged_at:
            out.append(merged_at[i])
        elif i not in consumed:
            out.append(item)
    return out


def _build_tree(oqo: OQO, resolver=None) -> OQLRenderTree:
    """OQO -> canonical `oql_render` tree. `render()` stringifies this; the two
    never drift (Invariant A by construction)."""
    head = EntityHead(id=oqo.get_rows, text=oqo.get_rows.lower())
    # Corpus selector parenthetical (#481). Canonical phrase for non-core; "" for
    # core (the default ⇒ omitted, so a core OQO round-trips to the bare entity).
    corpus_phrase = ""
    if getattr(oqo, "corpus", "core") and oqo.corpus != "core":
        corpus_phrase = f" ({CORPUS_CANONICAL_PHRASE.get(oqo.corpus, oqo.corpus)})"
    where_keyword = ""
    where = None
    if oqo.filter_rows:
        where_keyword = " where "
        # A same-column inclusive bound pair (`>= 2019` AND `<= 2023`) stays as two
        # endpoint clauses — the dash range render was removed (decision 24).
        rows = _merge_same_field_items(oqo.filter_rows, "and")  # decision 20
        if len(rows) == 1:
            where = _filter_node(rows[0], top=True, resolver=resolver)
        else:
            # The implicit-AND body renders as an infix `and` list (no wrapper).
            children = [_filter_node(f, top=False, resolver=resolver) for f in rows]
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
    if oqo.sample:
        segs = [_seg("value", str(oqo.sample), value=oqo.sample)]
        if oqo.seed is not None:
            segs.append(_seg("text", " seed "))
            segs.append(_seg("value", str(oqo.seed), value=oqo.seed))
        directives.append(SampleDirective(
            prefix="sample ", segments=segs, meta=SampleMeta(n=oqo.sample)))

    return OQLRenderTree(version="1.0", entity=head, where_keyword=where_keyword,
                         where=where, directives=directives,
                         corpus_phrase=corpus_phrase)


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
    """If `clause` is a factored group clause (`… has (a or b or …)` /
    `… is (a or b or …)`), return `(head, items, conn, close)` where `head` ends
    with `"("`, `items` is the list of top-level item strings, and `conn` is the
    group's connective (`"or"`/`"and"`); else None. Splits on
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
    return head, items, conn


def _split_group_text(text: str):
    """Split a paren-stripped group body into (top-level item strings,
    connective), or None if it isn't a splittable boolean. The string-level
    twin of `_split_list_clause`, used to recursively explode an over-width
    *item* (decision 20 merged clauses nest whole OR-blocks inside an AND).
    Connectives are matched only at paren depth 0, outside double quotes
    (quoted phrases / quoted-word escapes can contain literal `and`/`or`) and
    outside `[…]` display-name annotations (which can too)."""
    items, cur = [], []
    conn = None
    depth = bracket = 0
    in_q = False
    i, n = 0, len(text)
    while i < n:
        ch = text[i]
        if in_q:
            cur.append(ch)
            in_q = ch != '"'
            i += 1
            continue
        if ch == '"':
            in_q = True
        elif bracket == 0:
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
            elif ch == "[":
                bracket += 1
            elif depth == 0 and ch == " ":
                for word in (" or ", " and "):
                    if text.startswith(word, i):
                        items.append("".join(cur))
                        cur = []
                        conn = word.strip()
                        i += len(word)
                        break
                else:
                    cur.append(ch)
                    i += 1
                continue
        elif ch == "]":
            bracket -= 1
        cur.append(ch)
        i += 1
    items.append("".join(cur))
    if conn is None or len(items) < 2 or in_q or depth or bracket:
        return None
    return items, conn


def _fmt_group_item(it: str, indent: int, width: int, leading: str) -> str:
    """Lay out one exploded-group item at `indent`, with the parent's leading
    connective (`"and "` / `"or "` / empty for the first item) prefixed to its
    first line. An item that fits stays on one line; an over-width parenthesized
    sub-group explodes recursively (its open paren carries the leading
    connective, its closing paren sits back at `indent`)."""
    pad = " " * indent
    if len(pad) + len(leading) + len(it) <= width:
        return f"{pad}{leading}{it}"
    if it.startswith("(") and it.endswith(")"):
        parts = _split_group_text(it[1:-1])
        if parts is not None:
            sub_items, sub_conn = parts
            return _fmt_list(f"{pad}{leading}(", sub_items, sub_conn,
                             indent, width)
    return f"{pad}{leading}{it}"   # unbreakable (e.g. one long term)


def _fmt_list(head: str, items, conn: str, indent: int, width: int) -> str:
    """Lay out an exploded factored group. `indent` is the clause's own indent
    (where the closing `)` sits); items sit at `indent + _INDENT`. The connective
    LEADS every item but the first — i.e. a wrapped/exploded line begins with
    `and`/`or` (decision 25; matches the leading-connective `where` body, and
    `and`/`or` are infix, never terminal, so a trailing form would dirty two
    lines on append where leading dirties one). The parser is whitespace-blind,
    so the multi-line form re-parses to the identical OQO. >8 items that all fit
    -> fill/pack to `width`; otherwise one per line, recursively exploding any
    over-width sub-group item (decision 20 merged clauses nest whole OR-blocks
    inside an AND)."""
    pad = " " * (indent + _INDENT)
    out = [head]
    n = len(items)

    def piece(i, it):
        return it if i == 0 else f"{conn} {it}"

    all_fit = all(len(pad) + len(conn) + 1 + len(it) <= width for it in items)
    if n > 8 and all_fit:
        line, empty = pad, True
        for i, it in enumerate(items):
            p = piece(i, it)
            if not empty and len(line) + 1 + len(p) > width:
                out.append(line)
                line, empty = pad, True
            line = f"{pad}{p}" if empty else f"{line} {p}"
            empty = False
        out.append(line)
    else:
        lead = f"{conn} "
        out.extend(_fmt_group_item(it, indent + _INDENT, width,
                                   "" if i == 0 else lead)
                   for i, it in enumerate(items))
    out.append(f"{' ' * indent})")
    return "\n".join(out)


def _fmt_clause(clause: ClauseNode, indent: int, col: int, width: int) -> str:
    flat = _stringify_clause(clause)
    if col + len(flat) <= width:
        return flat
    parts = _split_list_clause(clause)
    if parts is None:
        return flat   # an unbreakable clause (e.g. one long search term)
    head, items, conn = parts
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
        # e.g. "works where " or "works (all corpora) where "
        prefix = f"{tree.entity.text}{tree.corpus_phrase}{tree.where_keyword}"
        body = _fmt_expr(tree.where, _INDENT, len(prefix), width)
        lines.append(f"{prefix}{body}")
    else:
        lines.append(f"{tree.entity.text}{tree.corpus_phrase}")
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
    return render_tree(oqo, resolver)[0]
