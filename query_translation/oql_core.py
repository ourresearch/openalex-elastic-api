"""OQL core v3: the scaled-back, English-first surface (oxjob #1555, Jason 2026-10-11).

Three sentences over the same OQO and engine:

    get <works phrase>[, <order>]                       a list of works
    get <things phrase>[, <order>]                      things by their own fields
    get the <measure>[ and <measure>] of <works>        one or a few numbers
    rank <things phrase> by <measure>[, lowest first]   things in order of a number
    break down <works phrase> by <dim>[ and <dim>]      one body of work, sliced

plus optional `Show ...` (extra columns) and `Only ...` (a threshold on the rank's own
number) sentences. The spec is #1555 `work/core_v3_spec.md`; its 44 cases are
`tests/oql/core_v3_cases.json`.

This module renders (OQO -> text) and parses (text -> OQO). The parser chunks the
English phrase into slots and hands each slot's conditions to today's parser as
key-value OQL, so leaf semantics (searches, links, years) stay in one place.
`render_core` returns None for an OQO that uses anything outside the core (walks,
condition groups, bins); callers fall back to today's echo.
"""
from __future__ import annotations

import re
from typing import Callable, Dict, List, Optional, Tuple

from query_translation import oql_lang as L
from query_translation.oql_pipeline import _COUNT_WORDS, _entity_type, _expr_text, english_list, link_text
from query_translation.oqo import (OQO, AffiliationFilter, BranchFilter, GroupBy, LeafFilter,
                                   Measure, MeasureFilter, SortBy)
from query_translation.walks import link_for

# ---------------------------------------------------------------------------
# Vocabulary
# ---------------------------------------------------------------------------
# Works columns whose single value can be the possessive star (`[UBC]'s works`).
STAR_COLUMNS = ("authorships.institutions.lineage", "authorships.countries", "authorships.author.id")
# Works columns whose `or` list of values reads `A or B` in the phrase.
OR_LIST_COLUMNS = ("funders.id", "primary_location.source.id", "authorships.institutions.lineage",
                   "authorships.countries")

TYPE_NOUNS = {"article": "articles", "review": "reviews", "preprint": "preprints", "book": "books",
              "book-chapter": "book chapters", "dataset": "datasets",
              "conference-paper": "conference papers", "dissertation": "dissertations",
              "editorial": "editorials", "letter": "letters", "report": "reports"}
NOUN_TYPES = {v: k for k, v in TYPE_NOUNS.items()}

# yes/no works columns that read as adjectives before the noun
ADJECTIVES = {"open_access.is_oa": "open access", "is_retracted": "retracted",
              "citation_normalized_percentile.is_in_top_1_percent": "top 1% cited",
              "citation_normalized_percentile.is_in_top_10_percent": "top 10% cited"}

# negative yes/no words before the noun (cow paths, writing test 2026-10-11)
NEG_ADJECTIVES = {"is_retracted": "non-retracted", "open_access.is_oa": "closed access"}

# search bases: `about` (title, abstract, keywords) or `with ... in the <place>`
SEARCH_PLACES = {"title_abstract_keywords": None, "display_name": "the title",
                 "abstract": "the abstract", "fulltext": "the full text",
                 "title_and_abstract": "the title or abstract"}
# the parser's bridge: a place's key-value search word (`with X in the title` -> `title has X`)
SEARCH_FIELD_FOR = {place: L._search_word_of(base) for base, place in SEARCH_PLACES.items() if place}
_PLACES_LONGEST = sorted(SEARCH_FIELD_FOR, key=lambda w: -len(w.split()))

# `in <key> [X]`: classification values that don't say their kind (Jason's #95 rule). Only
# the primary topic's columns: any of a work's topics (`topics.id`) reads in the `where`
# fallback, so the echo never covers which one it is (Jason 2026-10-12, no hidden keys)
IN_KEYS = {"sustainable_development_goals.id": "SDG",
           "primary_topic.id": "the topic", "primary_topic.subfield.id": "the subfield",
           "primary_topic.field.id": "the field", "primary_topic.domain.id": "the domain"}

# a list of things in a classification (`topics in the subfield [AI]`), both ways
THING_IN_KEYS = {"subfield.id": "the subfield", "field.id": "the field", "domain.id": "the domain"}
KEY_THING_IN = {v: k for k, v in THING_IN_KEYS.items()}

# breakdown dimensions
DIMS = {"publication_year": "year", "sustainable_development_goals.id": "SDG",
        "primary_topic.field.id": "field", "primary_topic.subfield.id": "subfield",
        "primary_topic.domain.id": "domain", "primary_topic.id": "topic", "type": "type",
        "open_access.is_oa": "open access", "open_access.oa_status": "open access status",
        "authorships.countries": "country", "authorships.institutions.lineage": "institution",
        "primary_location.source.id": "source", "funders.id": "funder",
        "primary_location.source.host_organization_lineage": "publisher",
        "language": "language", "corresponding_author_ids": "corresponding author",
        "is_retracted": "retracted"}
DIM_COLUMNS = {v: k for k, v in DIMS.items()}
_DIMS_LONGEST = sorted(DIM_COLUMNS, key=len, reverse=True)
_DIM_SPLIT = re.compile(r"\s+and\s+(?=(?:%s)\b)" % "|".join(re.escape(w) for w in _DIMS_LONGEST))
_TYPE_NOUNS_LONGEST = sorted(NOUN_TYPES, key=lambda n: -len(n.split()))

# rank: group column -> the things' plural noun
THING_NOUNS = {"authorships.author.id": "authors", "authorships.institutions.lineage": "institutions",
               "authorships.countries": "countries", "primary_location.source.id": "sources",
               "primary_topic.id": "topics", "primary_topic.field.id": "fields",
               "primary_topic.subfield.id": "subfields", "funders.id": "funders",
               "primary_location.source.host_organization_lineage": "publishers"}
# a type on the things that has its own noun
THING_TYPE_NOUNS = {("institutions", "company"): "companies", ("sources", "journal"): "journals",
                    ("sources", "repository"): "repositories"}
NOUN_THINGS = {v: k for k, v in THING_NOUNS.items()}
NOUN_THING_TYPES = {v: k for k, v in THING_TYPE_NOUNS.items()}

# measures: (measure, column) -> name
MEASURE_NAMES = {("count", None): "count of works",
                 ("sum", "cited_by_count"): "sum of citations",
                 ("sum", "apc_paid.value"): "sum of APCs paid",
                 ("mean", "fwci"): "mean FWCI", ("median", "fwci"): "median FWCI",
                 ("mean", "cited_by_count"): "mean citations",
                 ("median", "cited_by_count"): "median citations",
                 ("percent", "is_retracted"): "percent retracted",
                 ("percent", "open_access.is_oa"): "percent open access",
                 ("percent", "has_abstract"): "percent with an abstract",
                 ("percent", "has_fulltext"): "percent with full text",
                 ("percent", "has_doi"): "percent with a DOI",
                 ("percent_of_those", None): "share of the total",
                 ("value", "summary_stats.h_index"): "h-index",
                 ("value", "works_count"): "works count"}
for _col, _adj in ADJECTIVES.items():
    MEASURE_NAMES.setdefault(("percent", _col), f"percent {_adj}")
NAME_MEASURES = {v: k for k, v in MEASURE_NAMES.items()}
_MEASURES_LONGEST = sorted(NAME_MEASURES, key=len, reverse=True)
# the preposition a rank measure takes before its works phrase
MEASURE_JOIN = {"sum of citations": "to", "sum of APCs paid": "for"}

DEFAULT_BREAKDOWN = [("count", None), ("percent_of_those", None)]


def _default_breakdown() -> List[Measure]:
    return [Measure(*k) for k in DEFAULT_BREAKDOWN]

# own numeric fields of things, for `with an h-index above 50` and rank by own field
OWN_FIELDS = {"summary_stats.h_index": ("an h-index", "h-index"),
              "summary_stats.i10_index": ("an i10-index", "i10-index"),
              "works_count": ("a works count", "works count"),
              "cited_by_count": ("a citation count", "citation count")}
OWN_FIELD_BY_WORD = {v[1]: k for k, v in OWN_FIELDS.items()}

# order phrases for a list: (column, direction) -> words
ORDERS = {("cited_by_count", "desc"): "most cited first", ("cited_by_count", "asc"): "least cited first",
          ("publication_date", "desc"): "newest first", ("publication_date", "asc"): "oldest first",
          ("relevance_score", "desc"): "best matches first", ("fwci", "desc"): "highest FWCI first",
          ("fwci", "asc"): "lowest FWCI first", ("display_name", "asc"): "alphabetical by title"}
ORDER_PHRASES = {v: k for k, v in ORDERS.items()}

COMPARATOR_WORDS = _COUNT_WORDS        # `with more than 10 works ...`
WORD_COMPARATORS = {v: k for k, v in COMPARATOR_WORDS.items()}
ABOVE_WORDS = L.NUMBER_WORDS            # `with an h-index above 50`
WORD_ABOVE = {v: k for k, v in ABOVE_WORDS.items()}
_OWN_THRESHOLD = re.compile(r"with (an?) ([\w\-]+(?: count)?) (above|at least|below|at most) ([\d,.]+)")

Resolver = Optional[Callable]


class NotCore(Exception):
    """The OQO (or text) uses something outside the core; fall back to today's form."""


# ---------------------------------------------------------------------------
# Rendering helpers
# ---------------------------------------------------------------------------
def _link(value, column_id: str, resolver: Resolver = None) -> str:
    if isinstance(value, str) and value.startswith("col_"):
        return link_text(value, "collections", resolver)
    name = None
    if resolver is not None:
        try:
            name = L._call_resolver(resolver, value, column_id) or None
        except Exception:  # noqa: BLE001 (a name is decoration)
            name = None
    text = link_text(value, _entity_type(column_id) or "", None, name=name)
    if column_id == "referenced_works":
        text = _short_title(text)
    return text


def _short_title(link: str, limit: int = 48) -> str:
    """A work's title cut at about `limit` characters on a word boundary, with an
    ellipsis; the ID in the link is the truth (Jason's #129 note)."""
    m = re.match(r"\[(.*)\]\((.*)\)$", link)
    if not m or len(m.group(1)) <= limit:
        return link
    cut = m.group(1)[:limit].rsplit(" ", 1)[0].rstrip(" ,;:")
    return f"[{cut}…]({m.group(2)})"


def _number(v) -> str:
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    if isinstance(v, int) and abs(v) >= 10000:
        return f"{v:,}"
    return str(v)


def _search_string(rows: List, resolver: Resolver = None) -> str:
    """Today's search-string text for rows on one search base, without `<field> has `."""
    text = _expr_text(rows, resolver)
    i = text.find(" has ")
    if i < 0:
        raise NotCore(f"unexpected search text: {text}")
    return _unwrap(text[i + len(" has "):])


_ONE_TERM = re.compile(r'\((\"[^"()]*\"|[^\s()"]+)\)')


def _unwrap(text: str) -> str:
    """One word or one quoted phrase needs no parentheses: `kelp`, `"forest decline"`."""
    m = _ONE_TERM.fullmatch(text)
    return m.group(1) if m else text


def _where_text(rows, resolver=None) -> str:
    return re.sub(r'(\bhas )' + _ONE_TERM.pattern, r"\1\2", _expr_text(rows, resolver))


def _years_text(ops: Dict[str, object], dates: bool = False) -> str:
    lo = ops.get(">=")
    hi = ops.get("<=")
    if "=" in ops:
        return f"from {ops['=']}"
    if lo is not None and hi is not None:
        return f"from {lo} through {hi}" if dates else f"from {lo}–{hi}"
    if lo is not None:
        return f"since {lo}"
    if hi is not None:
        return f"through {hi}"
    if "<" in ops:
        return f"before {ops['<']}"
    raise NotCore("year bounds")


# ---------------------------------------------------------------------------
# The works phrase
# ---------------------------------------------------------------------------
class _Leftover(Exception):
    """A works column with no phrase: it goes into the `where` clause."""


class _Works:
    """Slots of a works phrase, read from an AND list of filters. The one institution,
    country or person that defines the set is the possessive star; a column with no
    phrase goes to `where`."""

    def __init__(self, rows: List, resolver: Resolver = None, possessive: bool = True,
                 thing: Optional[str] = None):
        self.resolver = resolver
        self.adjectives: List[str] = []
        self.type_noun = "works"
        self.years: Dict[str, object] = {}
        self.dates: Dict[str, object] = {}
        self.searches: Dict[str, List] = {}
        self.parts: Dict[str, List[str]] = {}
        self.where: List = []
        self.authors: List = []
        singles = [f for f in rows if isinstance(f, LeafFilter) and not f.is_negated
                   and f.operator == "is" and f.column_id in STAR_COLUMNS
                   and isinstance(f.value, str)]
        self.star = singles[0] if possessive and len(singles) == 1 else None
        for f in rows:
            if f is self.star:
                continue
            try:
                self._read_one(f, thing)
            except _Leftover:
                self.where.append(f)

    def _add(self, slot: str, text: str):
        self.parts.setdefault(slot, []).append(text)

    def _read_one(self, f, thing):
        r = self.resolver
        base = L._search_base(f)
        if base in SEARCH_PLACES:
            self.searches.setdefault(base, []).append(f)
            return
        if isinstance(f, BranchFilter):
            # an `or` list of one column's values reads `A or B` (funders, sources)
            if (f.join == "or" and not f.is_negated
                    and all(isinstance(lf, LeafFilter) and lf.operator == "is"
                            and not lf.is_negated for lf in f.filters)
                    and len({lf.column_id for lf in f.filters}) == 1):
                col = f.filters[0].column_id
                if col in OR_LIST_COLUMNS:
                    self._slot_for(col, " or ".join(_link(lf.value, col, r) for lf in f.filters), thing)
                    return
            raise _Leftover()
        if (isinstance(f, LeafFilter) and f.column_id in NEG_ADJECTIVES and f.operator == "is"
                and isinstance(f.value, bool) and f.is_negated == f.value):
            self.adjectives.append(NEG_ADJECTIVES[f.column_id])     # `it's not retracted`
            return
        if not isinstance(f, LeafFilter) or f.is_negated:
            raise _Leftover()
        col, val, op = f.column_id, f.value, f.operator
        if col in ADJECTIVES and val is True and op == "is":
            self.adjectives.append(ADJECTIVES[col])
        elif col == "type" and op == "is" and val in TYPE_NOUNS and self.type_noun == "works":
            self.type_noun = TYPE_NOUNS[val]
        elif col == "publication_year" and isinstance(val, int):
            key = {"is": "=", ">=": ">=", "<=": "<=", "<": "<", ">": ">="}.get(op)
            if key is None:
                raise _Leftover()
            self.years[key] = val + 1 if op == ">" else val
        elif col in ("from_publication_date", "to_publication_date") and op == "is":
            self.dates[">=" if col.startswith("from") else "<="] = val
        elif op == "in collection":
            if col == "referenced_works":
                self._add("citing", f"citing works in the collection {_link(val, col, r)}")
            else:
                self._add("in", f"in the collection {_link(val, col, r)}")
        elif op != "is" or isinstance(val, OQO):
            raise _Leftover()
        elif col == "authorships.author.id":
            self.authors.append(val)
        else:
            self._slot_for(col, _link(val, col, r), thing)

    def _slot_for(self, col, link, thing):
        if col == "authorships.institutions.lineage":
            self._add("from", f"co-authored with {link}" if thing == "institutions" else f"from {link}")
        elif col in ("authorships.countries", "authorships.institutions.continent"):
            self._add("from", f"from {link}")
        elif col == "corresponding_author_ids":
            self._add("role", f"with {link} as corresponding author")
        elif col == "primary_location.source.id":
            self._add("in", f"in {link}")
        elif col in IN_KEYS:
            self._add("in", f"in {IN_KEYS[col]} {link}")
        elif col == "funders.id":
            self._add("funded", f"funded by {link}")
        elif col == "primary_location.source.host_organization_lineage":
            self._add("published", f"published by {link}")
        elif col == "primary_location.license":
            self._add("license", f"under the {link} license")
        elif col == "referenced_works":
            self._add("citing", f"citing {link}")
        else:
            raise _Leftover()

    def time_text(self) -> str:
        if self.dates:
            return _years_text(self.dates, dates=True)
        if self.years:
            return _years_text(self.years)
        return ""

    def text(self, all_works: bool = False, keep_time: bool = True) -> str:
        r = self.resolver
        words: List[str] = []
        if self.star is not None:
            words.append(_link(self.star.value, self.star.column_id, r) + "'s")
        words += self.adjectives
        noun = self.type_noun
        if all_works and noun == "works" and not self._has_conditions():
            noun = "all works"
        words.append(noun)
        if keep_time and self.time_text():
            words.append(self.time_text())
        for base in SEARCH_PLACES:
            if base in self.searches:
                s = _search_string(self.searches[base], r)
                words.append(f"about {s}" if SEARCH_PLACES[base] is None
                             else f"with {s} in {SEARCH_PLACES[base]}")
        words += self.parts.get("citing", [])
        words += self.parts.get("from", [])
        if len(self.authors) == 1:
            words.append(f"by {_link(self.authors[0], 'authorships.author.id', r)}")
        elif self.authors:
            words.append("co-authored by " + english_list(
                [_link(a, "authorships.author.id", r) for a in self.authors]))
        words += self.parts.get("role", [])
        for slot in ("in", "published", "funded", "license"):
            words += self.parts.get(slot, [])
        if self.where:
            words.append("where " + _where_text(self.where, r))
        return " ".join(words)

    def _has_conditions(self) -> bool:
        return bool(self.star or self.adjectives or self.searches or self.parts or self.where
                    or self.authors or self.years or self.dates)


_works = _Works


# ---------------------------------------------------------------------------
# Measures
# ---------------------------------------------------------------------------
def _measure_name(m: Measure) -> str:
    """A measure's name, from the one table the parser reads too (so the echo always
    parses back); any other measure keeps today's echo."""
    name = MEASURE_NAMES.get((m.measure, m.column_id))
    if name is None:
        raise NotCore(f"no core name for {m.measure} {m.column_id}")
    return name


def _show(measures: List[Measure]) -> str:
    return "Show " + english_list([_measure_name(m) for m in measures]) + "."


# ---------------------------------------------------------------------------
# The things phrase (rank, and lists of things)
# ---------------------------------------------------------------------------
def _thing_parts(where, noun: str, resolver=None) -> Tuple[str, List[str], List, Optional[MeasureFilter]]:
    """(noun, phrases, leftovers, count filter) from a group's `where` tree."""
    parts: List[str] = []
    left: List = []
    count = None
    for f in (_and_items(where) if where is not None else []):
        if (text := _record_text(f, resolver)) is not None:
            parts.append(text)
        elif isinstance(f, MeasureFilter) and f.measure == "count" and not f.is_negated \
                and f.operator in COMPARATOR_WORDS:
            count = f
        elif isinstance(f, LeafFilter) and f.column_id == "type" and not f.is_negated \
                and (noun, f.value) in THING_TYPE_NOUNS:
            noun = THING_TYPE_NOUNS[(noun, f.value)]
        elif isinstance(f, LeafFilter) and f.column_id == "country_code" and not f.is_negated:
            parts.append(f"in {_link(f.value, 'authorships.countries', resolver)}")
        elif _is_own_threshold(f):
            parts.append(_own_threshold_text(f))
        else:
            left.append(f)
    return noun, parts, left, count


def _and_items(node) -> List:
    if isinstance(node, BranchFilter) and node.join == "and" and not node.is_negated:
        return L._flatten_and(node)
    return [node]


def _is_own_threshold(f) -> bool:
    return (isinstance(f, LeafFilter) and f.column_id in OWN_FIELDS and f.operator in ABOVE_WORDS
            and not f.is_negated)


def _own_threshold_text(f: LeafFilter) -> str:
    """`with an h-index above 50`"""
    return f"with {OWN_FIELDS[f.column_id][0]} {ABOVE_WORDS[f.operator]} {_number(f.value)}"


def _record_text(f, resolver=None) -> Optional[str]:
    """An author's record as words, or None: `at [UBC](I141945490) in 2+ years since 2022`,
    as today's parser reads it. No years is any year, plain `at` / `in` (Jason 2026-10-12);
    today's parser keeps that as a plain leaf on the record's column."""
    if f.is_negated:
        return None
    if isinstance(f, AffiliationFilter):
        since, through, min_years = f.since, f.through, f.min_years
    elif isinstance(f, LeafFilter) and f.operator == "is" and f.column_id in L._AT_EVER.values():
        since = through = min_years = None
    else:
        return None
    country = f.column_id.endswith("country_code")
    link = _link(f.value, "authorships.countries" if country else "authorships.institutions.lineage",
                 resolver)
    years = {k: v for k, v in ((">=", since), ("<=", through)) if v is not None}
    return (f"in {link}" if country else f"at {link}") \
        + (f" in {min_years}+ years" if min_years else "") + (" " + _years_text(years) if years else "")


# ---------------------------------------------------------------------------
# Sentences
# ---------------------------------------------------------------------------
def render_core(oqo: OQO, resolver: Resolver = None) -> Optional[str]:
    """The core v3 echo of `oqo`, or None when it uses something outside the core."""
    try:
        return _render(oqo, resolver)
    except (NotCore, _Leftover):
        return None


def _render(oqo: OQO, resolver: Resolver) -> str:
    if oqo.walks or oqo.each or oqo.sample or (oqo.corpus and oqo.corpus != "core"):
        raise NotCore("walks, samples and other corpora")
    if any(g.conditions is not None or g.bins is not None for g in oqo.group_by):
        raise NotCore("condition groups and bins")
    if oqo.get_rows != "works":
        if oqo.group_by or oqo.calculate:
            raise NotCore("a non-works start with splits")
        return _things_list(oqo, resolver)
    if not oqo.group_by:
        if oqo.calculate:
            return _number_sentence(oqo, resolver)
        return _works_list(oqo, resolver)
    first = oqo.group_by[0]
    if len(oqo.group_by) == 1 and first.column_id in THING_NOUNS and first.values is None \
            and (oqo.sort_by or first.where is not None):
        return _rank(oqo, resolver)
    return _breakdown(oqo, resolver)


def _order_text(sort_by: List[SortBy]) -> str:
    if not sort_by:
        return ""
    s = sort_by[0]
    key = (s.column_id, s.direction)
    if key in ORDERS:
        return ", " + ORDERS[key]
    if s.column_id not in OWN_FIELDS:
        raise NotCore(f"no core words for sorting by {s.column_id}")   # it must parse back
    word = OWN_FIELDS[s.column_id][1]
    return f", {'highest' if s.direction == 'desc' else 'lowest'} {word} first"


def _works_list(oqo, resolver):
    w = _works(oqo.filter_rows, resolver)
    return "get " + w.text() + _order_text(oqo.sort_by)


def _number_sentence(oqo, resolver):
    w = _works(oqo.filter_rows, resolver)
    names = []
    for m in oqo.calculate:
        n = _measure_name(m)
        names.append("count" if n == "count of works" else n)
    join = "for" if names[-1] == "sum of APCs paid" else "of"
    return f"get the {english_list(names)} {join} {w.text()}"


def _things_list(oqo, resolver):
    noun = oqo.get_rows
    sort = oqo.sort_by[0] if oqo.sort_by else None
    by_own = sort is not None and sort.column_id in OWN_FIELDS
    parts, thresholds, only, left = [], [], [], []
    for f in oqo.filter_rows:
        if isinstance(f, LeafFilter) and f.column_id == "type" and not f.is_negated \
                and (noun, f.value) in THING_TYPE_NOUNS and noun == oqo.get_rows:
            noun = THING_TYPE_NOUNS[(noun, f.value)]
        elif (text := _record_text(f, resolver)) is not None:
            parts.append(text)
        elif isinstance(f, LeafFilter) and not f.is_negated and f.operator == "is" \
                and f.column_id in THING_IN_KEYS:
            parts.append(f"in {THING_IN_KEYS[f.column_id]} {_link(f.value, f.column_id, resolver)}")
        elif isinstance(f, LeafFilter) and not f.is_negated and f.operator == "is" \
                and f.column_id == "country_code":
            parts.append(f"in {_link(f.value, 'authorships.countries', resolver)}")
        elif _is_own_threshold(f):
            # a threshold on the rank's own number is its `Only ...` sentence (Jason's #logs note)
            (only if by_own and f.column_id == sort.column_id else thresholds).append(f)
        else:
            left.append(f)
    parts += [_own_threshold_text(f) for f in thresholds]
    if left:
        parts.append("where " + _where_text(left, resolver))
    phrase = " ".join([noun] + parts)
    if not by_own:
        return "get " + phrase + _order_text(oqo.sort_by)
    text = f"rank {phrase} by {OWN_FIELDS[sort.column_id][1]}"
    if sort.direction == "asc":
        text += ", lowest first"
    return text + "".join(f". Only {noun} {_own_threshold_text(f)}." for f in only)


def _rank(oqo, resolver):
    g = oqo.group_by[0]
    thing = THING_NOUNS[g.column_id]
    noun, parts, left, count = _thing_parts(g.where, thing, resolver)
    if left:
        raise NotCore("a things filter with no phrase")
    works_text = _works(oqo.filter_rows, resolver, possessive=False, thing=thing).text()
    if count is not None:
        parts.append(f"with {COMPARATOR_WORDS[count.operator]} {_number(count.value)} {works_text}")
    measures = list(oqo.calculate) or [Measure("count")]
    sort = oqo.sort_by[0] if oqo.sort_by else None
    ranked = next((m for m in measures if sort is not None and m.key == sort.column_id), measures[0])
    rest = [m for m in measures if m is not ranked]
    name = _measure_name(ranked)
    if name == "count of works":
        # with a count filter, the rank is by that count and needs no `by`
        by = None if count is not None else f"count of {works_text}"
    elif count is not None or works_text == "works":
        by = name
    else:
        by = f"{name} {MEASURE_JOIN.get(name, 'of')} {works_text}"
    text = f"rank {' '.join([noun] + parts)}" + (f" by {by}" if by else "")
    if sort is not None and sort.direction == "asc":
        text += ", lowest first"
    return text + (". " + _show(rest) if rest else "")


def _breakdown(oqo, resolver):
    if len(oqo.group_by) > 2:
        raise NotCore("three dimensions")
    if any(g.where is not None or g.column_id not in DIMS for g in oqo.group_by):
        raise NotCore("a dimension with no word")
    year_dim = any(g.column_id == "publication_year" for g in oqo.group_by)
    w = _works(oqo.filter_rows, resolver)
    dims = sorted(oqo.group_by, key=lambda g: 0 if g.column_id == "publication_year" else 1)
    texts = []
    for g in dims:
        word = DIMS[g.column_id]
        if g.column_id == "publication_year" and w.time_text():
            word += " " + w.time_text()
        if g.values is not None:
            if len(g.values) == 1 and isinstance(g.values[0], str) and g.values[0].startswith("col_"):
                word += f" in the collection {_link(g.values[0], g.column_id, resolver)}"
            else:
                word += " in (" + ", ".join(_link(v, g.column_id, resolver) for v in g.values) + ")"
        texts.append(word)
    phrase = w.text(all_works=True, keep_time=not year_dim)
    text = f"break down {phrase} by {' and '.join(texts)}"
    keys = [(m.measure, m.column_id) for m in oqo.calculate]
    if oqo.calculate and keys not in (DEFAULT_BREAKDOWN, [("count", None)]):
        text += ". " + _show(oqo.calculate)
    return text


# ===========================================================================
# Parsing: text -> OQO
# ===========================================================================
_LINK = re.compile(r"\[([^\[\]]*)\]\(([^()\s]+)\)")
_QUOTE = re.compile(r'"[^"]*"')


class _Text:
    """The statement with links, quoted strings and parenthesized groups held aside as
    single tokens (⟦L0⟧, ⟦Q0⟧, ⟦P0⟧), so the phrase grammar reads plain words."""

    def __init__(self, text: str):
        self.links: List[Tuple[str, str]] = []
        self.chunks: List[str] = []
        text = " ".join(text.split())
        text = _LINK.sub(self._keep_link, text)
        text = _QUOTE.sub(self._keep, text)
        self.text = self._groups(text)

    def _keep_link(self, m):
        self.links.append((m.group(1), m.group(2)))
        return f"⟦L{len(self.links) - 1}⟧"

    def _keep(self, m):
        self.chunks.append(m.group(0))
        return f"⟦Q{len(self.chunks) - 1}⟧"

    def _groups(self, text: str) -> str:
        out, depth, start = [], 0, 0
        for i, ch in enumerate(text):
            if ch == "(":
                if depth == 0:
                    start = i
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth < 0:
                    raise NotCore("unbalanced parentheses")
                if depth == 0:
                    self.chunks.append(text[start:i + 1])
                    out.append(f"⟦Q{len(self.chunks) - 1}⟧")
                continue
            if depth == 0:
                out.append(ch)
        if depth:
            raise NotCore("unbalanced parentheses")
        return "".join(out)

    def restore(self, s: str) -> str:
        """The original text of a held-aside span (links back as `[name](ID)`)."""
        while "⟦Q" in s:
            s = re.sub(r"⟦Q(\d+)⟧", lambda m: self.chunks[int(m.group(1))], s)
        return re.sub(r"⟦L(\d+)⟧", lambda m: "[%s](%s)" % self.links[int(m.group(1))], s)

    def link_id(self, tok: str) -> Optional[str]:
        m = re.fullmatch(r"⟦L(\d+)⟧(?:'s)?", tok)
        return self.links[int(m.group(1))][1] if m else None


_KINDS = ("institutions", "authors", "sources", "funders", "publishers", "topics", "works",
          "continents", "countries")


def _kind_of(id_: str) -> Optional[str]:
    """The entity an ID's shape names (`I1` institutions, `KE` countries, `Q48`
    continents), from today's parser's table of ID shapes."""
    if id_.startswith("col_"):
        return "collections"
    return next((k for k in _KINDS if L._is_entity_id(k, id_)), None)


def _works_column(kind: Optional[str]) -> Optional[str]:
    """The works column a thing of this kind narrows (`institutions` -> lineage)."""
    if kind == "continents":
        return "authorships.institutions.continent"
    return link_for(kind) if kind else None


_YEAR = r"(\d{4})"
_RANGE = re.compile(r"(\d{4})\s*[–-]\s*(\d{4})$")
_DATE = r"(\d{4}-\d{2}-\d{2})"


def _old_filters(entity: str, condition: str) -> List:
    """Today's parser on one key-value condition list: its filter_rows."""
    from query_translation.oql_lang import parse
    oqo = parse(f"get {entity} where {condition}")
    return list(oqo.filter_rows)


class _Words:
    """A cursor over the protected text's words."""

    def __init__(self, t: _Text, s: str):
        self.t = t
        # a list's comma is its own word (`[A], [B], and [C]`); `1,000` stays whole
        self.w = re.sub(r",(?!\d)", " , ", s).split()
        self.i = 0

    def peek(self, n=0) -> Optional[str]:
        j = self.i + n
        return self.w[j] if j < len(self.w) else None

    def at(self, *words) -> bool:
        return all(self.peek(k) is not None and self.peek(k).lower() == w.lower()
                   for k, w in enumerate(words))

    def take(self, n=1) -> List[str]:
        if self.i + n > len(self.w):
            raise NotCore("the sentence ends too soon")
        out = self.w[self.i:self.i + n]
        self.i += n
        return out

    def done(self) -> bool:
        return self.i >= len(self.w)

    def rest(self) -> str:
        return " ".join(self.w[self.i:])


def _years_from(ws: _Words, col: str = "publication_year") -> Optional[List[LeafFilter]]:
    """since 2020 | from 2022 | from 2018–2025 | before 2010 | through 2024 |
    published ... | dates: since 2021-06-01, from D through D."""
    if ws.at("published"):
        save = ws.i
        ws.take()
        got = _years_from(ws, col)
        if got is None:
            ws.i = save
        return got
    a, b = ws.peek(), ws.peek(1)
    if a is None or b is None:
        return None
    a = a.lower()
    if a == "from" and re.fullmatch(_DATE, b) and ws.at("from", b, "through") and ws.peek(3) \
            and re.fullmatch(_DATE, ws.peek(3)):
        d1, d2 = b, ws.peek(3)
        ws.take(4)
        return [LeafFilter("from_publication_date", d1), LeafFilter("to_publication_date", d2)]
    if a in ("since", "through") and re.fullmatch(_DATE, b):
        ws.take(2)
        return [LeafFilter("from_publication_date" if a == "since" else "to_publication_date", b)]
    if a == "from" and _RANGE.match(b):
        m = _RANGE.match(b)
        ws.take(2)
        return [LeafFilter(col, int(m.group(1)), ">="), LeafFilter(col, int(m.group(2)), "<=")]
    if a == "from" and re.fullmatch(_YEAR, b) and ws.at("from", b, "through") and ws.peek(3) \
            and re.fullmatch(_YEAR, ws.peek(3)):
        y1, y2 = int(b), int(ws.peek(3))
        ws.take(4)
        return [LeafFilter(col, y1, ">="), LeafFilter(col, y2, "<=")]
    if re.fullmatch(_YEAR, b) and a in ("since", "from", "in", "before", "through"):
        ws.take(2)
        op = {"since": ">=", "from": "is", "in": "is", "before": "<", "through": "<="}[a]
        return [LeafFilter(col, int(b), op)]
    return None


def _links_list(ws: _Words, sep: str = "or") -> List[str]:
    """⟦L0⟧ [or ⟦L1⟧ ...] -> IDs."""
    ids = []
    while True:
        id_ = ws.t.link_id(ws.peek() or "")
        if id_ is None:
            break
        ws.take()
        ids.append(id_)
        if ws.at(sep) and ws.t.link_id(ws.peek(1) or ""):
            ws.take()
            continue
        break
    return ids


def _any_of(col: str, ids: List[str]):
    leaves = [LeafFilter(col, i) for i in ids]
    return leaves[0] if len(leaves) == 1 else BranchFilter(join="or", filters=leaves)


_ADJECTIVE_WORDS = ([(c, a.split(), False) for c, a in NEG_ADJECTIVES.items()]
                    + [(c, a.split(), True) for c, a in ADJECTIVES.items()])


def _parse_works(t: _Text, s: str, collection_type: Optional[Callable] = None,
                 thing: Optional[str] = None) -> List:
    """A works phrase -> its filters (an AND list)."""
    ws = _Words(t, s)
    rows: List = []
    # possessive star
    tok = ws.peek() or ""
    if tok.endswith("'s") and t.link_id(tok):
        id_ = t.link_id(tok)
        col = _works_column(_kind_of(id_))
        if col not in STAR_COLUMNS:
            raise NotCore(f"a possessive on {id_}")
        rows.append(LeafFilter(col, id_))
        ws.take()
    # adjectives
    while True:
        hit = next(((c, w, v) for c, w, v in _ADJECTIVE_WORDS if ws.at(*w)), None)
        if hit is None:
            break
        rows.append(LeafFilter(hit[0], hit[2]))
        ws.take(len(hit[1]))
    # the type noun
    if ws.at("all", "works"):
        ws.take(2)
    else:
        if ws.at("all"):
            ws.take()
        for noun in _TYPE_NOUNS_LONGEST:
            if ws.at(*noun.split()):
                rows.append(LeafFilter("type", NOUN_TYPES[noun]))
                ws.take(len(noun.split()))
                break
        else:
            if ws.at("works"):
                ws.take()
            else:
                raise NotCore(f"expected works or a type of work, got {ws.peek()!r}")
    # the slots, in any order
    while not ws.done():
        yrs = _years_from(ws)
        if yrs is not None:
            rows += yrs
            continue
        if ws.at("about"):
            ws.take()
            s_tok = ws.take()[0]
            rows += _old_filters("works", f"title-abstract-keywords has {t.restore(s_tok)}")
            continue
        if ws.at("with") and not ws.at("with", "an") and t.link_id(ws.peek(1) or "") is None:
            # with <search> in the title / abstract / full text / title or abstract
            save = ws.i
            ws.take()
            s_tok = ws.take()[0]
            place = None
            for words in _PLACES_LONGEST:
                if ws.at("in", *words.split()):
                    place = words
                    ws.take(1 + len(words.split()))
                    break
            if place is None:
                ws.i = save
                raise NotCore("`with` needs `in the title` (or abstract, full text)")
            rows += _old_filters("works", f"{SEARCH_FIELD_FOR[place]} has {t.restore(s_tok)}")
            continue
        if ws.at("with") and t.link_id(ws.peek(1) or "") and ws.at("with", ws.peek(1), "as",
                                                                   "corresponding", "author"):
            rows.append(LeafFilter("corresponding_author_ids", t.link_id(ws.peek(1))))
            ws.take(5)
            continue
        if ws.at("citing", "works", "in", "the", "collection"):
            ws.take(5)
            rows.append(LeafFilter("referenced_works", t.link_id(ws.take()[0]), "in collection"))
            continue
        if ws.at("citing"):
            ws.take()
            rows.append(_any_of("referenced_works", _links_list(ws)))
            continue
        if ws.at("co-authored", "with"):
            ws.take(2)
            rows.append(_any_of("authorships.institutions.lineage", _links_list(ws)))
            continue
        if ws.at("co-authored", "by"):
            ws.take(2)
            ids = []
            while t.link_id(ws.peek() or ""):   # `A, B, and C` or `A, B and C`
                ids.append(t.link_id(ws.take()[0]))
                if ws.at(","):
                    ws.take()
                if ws.at("and"):
                    ws.take()
            rows += [LeafFilter("authorships.author.id", i) for i in ids]
            continue
        if ws.at("from", "the", "collection") or (ws.at("from") and (t.link_id(ws.peek(1) or "") or "")
                                                  .startswith("col_")):
            ws.take(3 if ws.at("from", "the") else 1)
            rows.append(LeafFilter("authorships.institutions.lineage", t.link_id(ws.take()[0]),
                                   "in collection"))
            continue
        if ws.at("from"):
            ws.take()
            ids = _links_list(ws)
            if not ids:
                raise NotCore("`from` needs a place")
            kind = _kind_of(ids[0])
            if kind not in ("institutions", "countries", "continents"):
                raise NotCore(f"`from` {ids[0]}")
            col = _works_column(kind)
            rows.append(_any_of(col, ids))
            continue
        if ws.at("by") and t.link_id(ws.peek(1) or ""):
            ws.take()
            rows.append(_any_of("authorships.author.id", _links_list(ws)))
            continue
        if ws.at("in", "the", "collection"):
            ws.take(3)
            cid = t.link_id(ws.take()[0])
            ctype = collection_type(cid) if collection_type else None
            col = _works_column(ctype) if ctype not in (None, "works") else "id"
            rows.append(LeafFilter(col, cid, "in collection"))
            continue
        key_hit = None
        for col, key in IN_KEYS.items():
            if col.startswith("topics."):
                continue
            if ws.at("in", *key.split()) and t.link_id(ws.peek(1 + len(key.split())) or ""):
                key_hit = (col, len(key.split()))
                break
        if key_hit:
            ws.take(1 + key_hit[1])
            rows.append(_any_of(key_hit[0], _links_list(ws)))
            continue
        if ws.at("in") and t.link_id(ws.peek(1) or ""):
            ws.take()
            ids = _links_list(ws)
            if _kind_of(ids[0]) != "sources":
                raise NotCore(f"`in` {ids[0]}: name its kind (the topic, SDG, the collection)")
            rows.append(_any_of("primary_location.source.id", ids))
            continue
        if ws.at("published", "by"):
            ws.take(2)
            rows.append(_any_of("primary_location.source.host_organization_lineage", _links_list(ws)))
            continue
        if ws.at("funded", "by"):
            ws.take(2)
            rows.append(_any_of("funders.id", _links_list(ws)))
            continue
        if ws.at("under", "the") and t.link_id(ws.peek(2) or "") and ws.at("under", "the", ws.peek(2), "license"):
            rows.append(LeafFilter("primary_location.license", t.link_id(ws.peek(2))))
            ws.take(4)
            continue
        if ws.at("where"):
            ws.take()
            rest = t.restore(ws.rest())
            ws.i = len(ws.w)
            rows += _old_filters("works", rest)
            continue
        raise NotCore(f"unexpected {ws.peek()!r} in a works phrase")
    return rows


def _split_sentences(t: _Text) -> List[str]:
    parts = [p.strip() for p in re.split(r"\.\s+(?=(?:Show|Only)\b)", t.text.strip())]
    return [p[:-1] if p.endswith(".") else p for p in parts]


def _parse_measures(t: _Text, s: str) -> List[Measure]:
    # `a, b, and c` (the Oxford comma, canonical) or `a, b and c`
    names = [n.strip() for n in re.split(r",\s*(?:and\s+)?|\s+and\s+", s) if n.strip()]
    out = []
    for n in names:
        if n == "count":
            n = "count of works"
        if n not in NAME_MEASURES:
            raise NotCore(f"unknown measure {n!r}")
        m, col = NAME_MEASURES[n]
        out.append(Measure(m, col))
    return out


def _order(s: str) -> Tuple[str, List[SortBy]]:
    for phrase, (col, d) in ORDER_PHRASES.items():
        if s.endswith(", " + phrase):
            return s[: -len(phrase) - 2], [SortBy(col, d)]
    m = re.search(r", (highest|lowest) ([\w\- ]+?) first$", s)
    if m and m.group(2) in OWN_FIELD_BY_WORD:
        return s[: m.start()], [SortBy(OWN_FIELD_BY_WORD[m.group(2)],
                                       "desc" if m.group(1) == "highest" else "asc")]
    return s, []


_CORE_FIRST = re.compile(r"\s*(?:rank|break\s+down|get\s+the)\s", re.I)


def core_first(text: str) -> bool:
    """Sentences only core v3 has: try its parser before today's."""
    return _CORE_FIRST.match(text) is not None


def parse_core(text: str, collection_type: Optional[Callable] = None) -> OQO:
    """A core v3 statement -> OQO. Raises NotCore when the text isn't a core sentence."""
    t = _Text(text)
    sentences = _split_sentences(t)
    main, extras = sentences[0], sentences[1:]
    show = [e[len("Show "):] for e in extras if e.startswith("Show ")]
    only = [e[len("Only "):] for e in extras if e.startswith("Only ")]
    low = main.lower()
    if low.startswith("break down "):
        oqo = _parse_breakdown(t, main[len("break down "):], collection_type)
    elif low.startswith("rank "):
        oqo = _parse_rank(t, main[len("rank "):], collection_type, only)
    elif low.startswith("get the "):
        oqo = _parse_number(t, main[len("get the "):], collection_type)
    elif low.startswith("get "):
        oqo = _parse_get(t, main[len("get "):], collection_type)
    else:
        raise NotCore("not a core sentence")
    if show:
        extra = _parse_measures(t, show[0])
        if oqo.group_by and oqo.get_rows == "works" and not oqo.sort_by:
            oqo.calculate = extra                       # a breakdown's columns
        else:
            oqo.calculate = list(oqo.calculate) + extra
    return oqo


def _parse_get(t, s, collection_type):
    body, sort = _order(s)
    first = body.split()[0].lower() if body.split() else ""
    if (first in NOUN_THINGS or first in NOUN_THING_TYPES) and re.search(
            r" with (?:more than|at least|fewer than|at most|works|articles|\w+ works)\b", body):
        oqo = _parse_rank(t, body, collection_type, [])  # things with works: ranked by count
        return oqo
    if first in NOUN_THINGS or first in NOUN_THING_TYPES:
        oqo = _parse_things_list(t, body)
    else:
        oqo = OQO(get_rows="works", filter_rows=_parse_works(t, body, collection_type))
    oqo.sort_by = sort
    return oqo


def _parse_number(t, s, collection_type):
    # the measures end where a works phrase begins
    rest = None
    for mm in re.finditer(r" (of|for) ", s):
        cand = s[: mm.start()]
        try:
            measures = _parse_measures(t, cand)
        except NotCore:
            continue
        rest = s[mm.end():]
        break
    if rest is None:
        raise NotCore("unknown measures")
    return OQO(get_rows="works", filter_rows=_parse_works(t, rest, collection_type),
               calculate=measures)


def _parse_things(t, s) -> Tuple[str, Optional[str], List]:
    """noun [type] and the things' own conditions -> (group column, type, where items)."""
    ws = _Words(t, s)
    noun = ws.take()[0].lower()
    typ = None
    if noun in NOUN_THING_TYPES:
        base, typ = NOUN_THING_TYPES[noun]
        noun = base
    if noun not in NOUN_THINGS:
        raise NotCore(f"unknown things {noun!r}")
    items: List = []
    while not ws.done():
        if noun == "authors" and (ws.at("ever", "at") or ws.at("at") or ws.at("ever", "in") or (
                ws.at("in") and _kind_of(t.link_id(ws.peek(1) or "") or "") == "countries")):
            # an author's record: today's parser reads the place and its years, so `at [UBC]`
            # means what it means there (any year)
            start = ws.i
            ws.take(2 if ws.at("ever") else 1)
            ws.take()
            while True:                     # years and `in 2+ years`, in either order
                if ws.at("in") and re.fullmatch(r"\d\+", ws.peek(1) or "") and ws.at("in", ws.peek(1), "years"):
                    ws.take(3)
                elif _years_from(ws, "years") is None:
                    break
            items += list(L.parse("get authors " + t.restore(" ".join(ws.w[start:ws.i]))).filter_rows)
            continue
        if ws.at("in") and _kind_of(t.link_id(ws.peek(1) or "") or "") == "countries":
            ws.take()
            items.append(LeafFilter("country_code", t.link_id(ws.take()[0])))
            continue
        if ws.at("with", "works") or ws.at("with", "articles") or (ws.at("with") and (ws.peek(1) or "").lower()
                                                                in NOUN_TYPES):
            ws.take()
            items.append(("count", ">=", 1, ws.rest()))
            ws.i = len(ws.w)
            continue
        if ws.at("with") and " ".join(w for w in (ws.peek(1), ws.peek(2)) if w).lower() in WORD_COMPARATORS:
            ws.take()
            word = " ".join(ws.take(2)).lower()
            n = int(ws.take()[0].replace(",", ""))
            items.append(("count", WORD_COMPARATORS[word], n, ws.rest()))
            ws.i = len(ws.w)
            continue
        if ws.at("with"):
            got = _parse_own_threshold(ws.rest())
            if got is not None:
                items.append(got[0])
                ws.take(len(got[1].split()))
                continue
        raise NotCore(f"unexpected {ws.peek()!r} in a things phrase")
    return noun, typ, items


def _parse_own_threshold(s: str) -> Optional[Tuple[LeafFilter, str]]:
    """`with an h-index above 50 ...` -> (the filter, the words it took), or None."""
    m = _OWN_THRESHOLD.match(s)
    if not m or m.group(2) not in OWN_FIELD_BY_WORD:
        return None
    return LeafFilter(OWN_FIELD_BY_WORD[m.group(2)], _num(m.group(4)), WORD_ABOVE[m.group(3)]), m.group(0)


def _num(s: str):
    s = s.replace(",", "")
    return float(s) if "." in s else int(s)


def _parse_things_list(t, s) -> OQO:
    ws = _Words(t, s)
    noun = ws.peek().lower()
    if noun in NOUN_THING_TYPES:
        base, typ = NOUN_THING_TYPES[noun]
        inner = _parse_things_list(t, base + s[len(noun):])
        inner.filter_rows.insert(0, LeafFilter("type", typ))
        return inner
    entity = noun if noun in NOUN_THINGS else None
    if entity is None:
        raise NotCore(f"a list of {noun}")
    rows: List = []
    rest = " ".join(s.split()[1:])
    if rest.startswith("where "):
        return OQO(get_rows=entity, filter_rows=_old_filters(entity, t.restore(rest[len("where "):])))
    if rest == "":
        return OQO(get_rows=entity)
    m = re.match(r"in (the subfield|the field|the domain) (⟦L\d+⟧)$", rest)
    if m:
        col = KEY_THING_IN[m.group(1)]
        return OQO(get_rows=entity, filter_rows=[LeafFilter(col, t.link_id(m.group(2)))])
    _, _, items = _parse_things(t, s)
    for it in items:
        if isinstance(it, tuple):
            raise NotCore("a count of works on a plain list")
        rows.append(it)
    return OQO(get_rows=entity, filter_rows=rows)


_MEASURE_START = re.compile(r" by (count of|count\b|sum of|mean |median |percent |share of the total|"
                            r"h-index|i10-index|works count|citation count)")


def _parse_rank(t, s, collection_type, only):
    body, low = (s[: -len(", lowest first")], True) if s.endswith(", lowest first") else (s, False)
    m = _MEASURE_START.search(body)
    if m:
        things, measure = body[: m.start()], body[m.start() + len(" by "):]
    elif re.search(r" with (?:more than|at least|fewer than|at most|\w+ works|works) ", " " + body + " "):
        things, measure = body, "count of works"     # `rank authors with at least 5 works about X`
    else:
        raise NotCore("`rank <things> by <measure>`")
    direction = "asc" if low else "desc"
    # rank by an own field: a sorted list of things
    if measure in OWN_FIELD_BY_WORD:
        oqo = _parse_things_list(t, things)
        col = OWN_FIELD_BY_WORD[measure]
        for o in only:
            rest = o.split(" ", 1)[1] if " " in o else ""
            got = _parse_own_threshold(rest)
            if got is None or got[1] != rest:
                raise NotCore("`Only <things> with an <field> above N`")
            oqo.filter_rows.append(got[0])
        oqo.sort_by = [SortBy(col, direction)]
        return oqo
    noun, typ, items = _parse_things(t, things)
    where: List = []
    works_rows: List = []
    for it in items:
        if isinstance(it, tuple):
            _, op, n, phrase = it
            if not (op == ">=" and n == 1):
                where.append(MeasureFilter("count", op, n))
            works_rows += _parse_works(t, phrase, collection_type, thing=noun)
        else:
            where.append(it)
    if typ:
        where.append(LeafFilter("type", typ))
    # the measure, and the works it covers
    if measure == "count of works":
        ranked, phrase = "count of works", ""
    elif measure.startswith("count of "):
        ranked = "count of works"
        phrase = measure[len("count of "):]
    else:
        ranked = next((n for n in _MEASURES_LONGEST
                       if measure == n or measure.startswith(n + " ")), None)
        if ranked is None:
            raise NotCore(f"unknown measure in {measure!r}")
        tail = measure[len(ranked):].strip()
        join = MEASURE_JOIN.get(ranked, "of")
        if tail.startswith(join + " "):
            phrase = tail[len(join) + 1:]
        elif tail == "":
            phrase = ""
        else:
            raise NotCore(f"`{ranked} {join} <works>`")
    if phrase:
        works_rows += _parse_works(t, phrase, collection_type, thing=noun)
    mm, col = NAME_MEASURES[ranked]
    meas = Measure(mm, col)
    g = GroupBy(column_id=NOUN_THINGS[noun],
                where=(where[0] if len(where) == 1 else BranchFilter(join="and", filters=where))
                if where else None)
    return OQO(get_rows="works", filter_rows=works_rows, group_by=[g], calculate=[meas],
               sort_by=[SortBy(meas.key, direction)])


def _parse_breakdown(t, s, collection_type):
    # the works phrase ends at the ` by ` that opens the dimensions
    cut = None
    for mm in re.finditer(r" by ", s):
        nxt = s[mm.end():]
        if any(nxt == w or nxt.startswith(w + " ") for w in _DIMS_LONGEST):
            cut = mm
            break
    if cut is None:
        raise NotCore("`break down <works> by <dimension>`")
    phrase, dims_text = s[: cut.start()], s[cut.end():]
    rows = _parse_works(t, phrase, collection_type)
    groups: List[GroupBy] = []
    for part in _DIM_SPLIT.split(dims_text):
        word = next((w for w in _DIMS_LONGEST if part == w or part.startswith(w + " ")), None)
        if word is None:
            raise NotCore(f"unknown dimension {part!r}")
        col = DIM_COLUMNS[word]
        rest = part[len(word):].strip()
        g = GroupBy(column_id=col)
        if rest:
            ws = _Words(t, rest)
            if col == "publication_year":
                yrs = _years_from(ws)
                if yrs is None:
                    raise NotCore(f"after `by year`: {rest!r}")
                rows += yrs
            if ws.at("in", "the", "collection"):
                ws.take(3)
                g.values = [t.link_id(ws.take()[0])]
            elif ws.at("in"):
                ws.take()
                inner = t.restore(ws.take()[0])
                if not (inner.startswith("(") and inner.endswith(")")):
                    raise NotCore("a list of values in parentheses")
                g.values = [lk[1] for lk in _LINK.findall(inner)] or \
                    [v.strip() for v in inner[1:-1].split(",")]
            if not ws.done():
                raise NotCore(f"unexpected {ws.peek()!r} after a dimension")
        groups.append(g)
    return OQO(get_rows="works", filter_rows=rows, group_by=groups, calculate=_default_breakdown())


# ===========================================================================
# The automatic baseline (Jason, 2026-10-11 17:45 CT)
# ===========================================================================
BASELINE_COLUMNS = STAR_COLUMNS + ("primary_location.source.id", "funders.id")


def baseline_oqo(oqo: OQO) -> Optional[Tuple[OQO, LeafFilter]]:
    """For a breakdown narrowed by one named thing (an institution, country, person,
    journal or funder): the same breakdown with that thing removed and every other
    condition kept, measured as shares, and the filter it dropped. None otherwise
    (a rank, a plain list, two named things, or a split by that same thing)."""
    from dataclasses import replace
    if oqo.get_rows != "works" or not oqo.group_by or oqo.sort_by or oqo.walks or oqo.each:
        return None
    if any(g.where is not None or g.conditions is not None for g in oqo.group_by):
        return None
    named = [f for f in oqo.filter_rows
             if isinstance(f, LeafFilter) and f.column_id in BASELINE_COLUMNS]
    if len(named) != 1:
        return None
    star = named[0]
    if star.is_negated or star.operator != "is" or not isinstance(star.value, str) \
            or any(g.column_id == star.column_id for g in oqo.group_by):
        return None
    rest = [f for f in oqo.filter_rows if f is not star]
    return replace(oqo, filter_rows=rest, cursor=None, calculate=_default_breakdown()), star
