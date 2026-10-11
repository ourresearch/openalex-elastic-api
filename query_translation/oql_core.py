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

from query_translation.oqo import (OQO, AffiliationFilter, BranchFilter, GroupBy, LeafFilter,
                                   Measure, MeasureFilter, SortBy)

# ---------------------------------------------------------------------------
# Vocabulary
# ---------------------------------------------------------------------------
# Works columns whose single value can be the possessive star (`[UBC]'s works`).
STAR_COLUMNS = ("authorships.institutions.lineage", "authorships.countries", "authorships.author.id")

TYPE_NOUNS = {"article": "articles", "review": "reviews", "preprint": "preprints", "book": "books",
              "book-chapter": "book chapters", "dataset": "datasets",
              "conference-paper": "conference papers", "dissertation": "dissertations",
              "editorial": "editorials", "letter": "letters", "report": "reports"}
NOUN_TYPES = {v: k for k, v in TYPE_NOUNS.items()}

# yes/no works columns that read as adjectives before the noun
ADJECTIVES = {"open_access.is_oa": "open access", "is_retracted": "retracted",
              "citation_normalized_percentile.is_in_top_1_percent": "top 1% cited",
              "citation_normalized_percentile.is_in_top_10_percent": "top 10% cited"}

# search bases: `about` (title, abstract, keywords) or `with ... in the <place>`
SEARCH_PLACES = {"title_abstract_keywords": None, "display_name": "the title",
                 "abstract": "the abstract", "fulltext": "the full text",
                 "title_and_abstract": "the title or abstract"}
SEARCH_WORDS = {"title_abstract_keywords": "title-abstract-keywords", "display_name": "title",
                "abstract": "abstract", "fulltext": "full text",
                "title_and_abstract": "title-abstract"}

# `in <key> [X]`: classification values that don't say their kind (Jason's #95 rule)
IN_KEYS = {"sustainable_development_goals.id": "SDG",
           "primary_topic.id": "the topic", "topics.id": "the topic",
           "primary_topic.subfield.id": "the subfield", "topics.subfield.id": "the subfield",
           "primary_topic.field.id": "the field", "topics.field.id": "the field",
           "primary_topic.domain.id": "the domain", "topics.domain.id": "the domain"}

# key-value field words for each works column the phrase covers (the parser's bridge)
KV_WORDS = {"authorships.institutions.lineage": "institution", "authorships.countries": "country",
            "authorships.author.id": "author", "corresponding_author_ids": "corresponding author",
            "primary_location.source.id": "source", "sustainable_development_goals.id": "SDG",
            "primary_topic.id": "topic", "primary_topic.subfield.id": "subfield",
            "primary_topic.field.id": "field", "primary_topic.domain.id": "domain",
            "funders.id": "funder", "primary_location.source.host_organization_lineage": "publisher",
            "primary_location.license": "license", "referenced_works": "it cites",
            "type": "type"}

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
# get_rows entity for a things list
THING_ENTITIES = {"authors": "authors", "institutions": "institutions", "countries": "countries",
                  "sources": "sources", "topics": "topics", "funders": "funders",
                  "publishers": "publishers", "fields": "fields", "subfields": "subfields"}

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
NAME_MEASURES = {v: k for k, v in MEASURE_NAMES.items()}
# the preposition a rank measure takes before its works phrase
MEASURE_JOIN = {"sum of citations": "to", "sum of APCs paid": "for"}

DEFAULT_BREAKDOWN = [("count", None), ("percent_of_those", None)]

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

COMPARATOR_WORDS = {">": "more than", ">=": "at least", "<": "fewer than", "<=": "at most"}
WORD_COMPARATORS = {v: k for k, v in COMPARATOR_WORDS.items()}
ABOVE_WORDS = {">": "above", ">=": "at least", "<": "below", "<=": "at most"}

Resolver = Optional[Callable]


class NotCore(Exception):
    """The OQO (or text) uses something outside the core; fall back to today's form."""


# ---------------------------------------------------------------------------
# Rendering helpers
# ---------------------------------------------------------------------------
def _ns(column_id: str) -> Optional[str]:
    from query_translation import oql_lang as L
    return L.entity_type_for_column(column_id)


def _link(value, column_id: str, resolver: Resolver = None) -> str:
    from query_translation.oql_pipeline import link_text
    if isinstance(value, str) and value.startswith("col_"):
        return link_text(value, "collections", resolver)
    ns = _ns(column_id) or ""
    name = None
    if resolver is not None:
        try:
            name = resolver(value, column_id) or None
        except Exception:  # noqa: BLE001 (a name is decoration)
            name = None
    text = link_text(value, ns, resolver, name=name)
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


def _possessive(link: str) -> str:
    return link + "'s"


def _and_list(items: List[str]) -> str:
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + " and " + items[-1]


def _number(v) -> str:
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    if isinstance(v, int) and abs(v) >= 10000:
        return f"{v:,}"
    return str(v)


def _search_base(node) -> Optional[str]:
    """The search base when every leaf under `node` searches one column."""
    leaves = _leaves(node)
    bases = set()
    for lf in leaves:
        if not isinstance(lf, LeafFilter) or lf.operator != "has":
            return None
        cid = lf.column_id
        for suf in (".search.exact", ".search"):
            if cid.endswith(suf):
                bases.add(cid[: -len(suf)])
                break
        else:
            return None
    return bases.pop() if len(bases) == 1 else None


def _leaves(node) -> List:
    if isinstance(node, BranchFilter):
        out = []
        for f in node.filters:
            out += _leaves(f)
        return out
    return [node]


def _search_string(rows: List, resolver: Resolver = None) -> str:
    """Today's search-string text for rows on one search base, without `<field> has `."""
    from query_translation.oql_pipeline import _expr_text
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
    from query_translation.oql_pipeline import _expr_text
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
class _Works:
    """Slots of a works phrase, read from an AND list of filters."""

    def __init__(self, rows: List, resolver: Resolver = None, possessive: bool = True,
                 thing: Optional[str] = None, year_dim: bool = False):
        self.resolver = resolver
        self.star = None            # (column, value)
        self.adjectives: List[str] = []
        self.type_noun = "works"
        self.years: Dict[str, object] = {}
        self.dates: Dict[str, object] = {}
        self.searches: Dict[str, List] = {}
        self.parts: Dict[str, List[str]] = {}
        self.where: List = []
        self.authors: List = []
        self._read(rows, possessive, thing)
        self.year_dim = year_dim

    def _add(self, slot: str, text: str):
        self.parts.setdefault(slot, []).append(text)

    def _read(self, rows, possessive, thing):
        r = self.resolver
        singles = [f for f in rows if isinstance(f, LeafFilter) and not f.is_negated
                   and f.operator == "is" and f.column_id in STAR_COLUMNS
                   and isinstance(f.value, str)]
        if possessive and len(singles) == 1:
            self.star = singles[0]
        for f in rows:
            if f is self.star:
                continue
            base = _search_base(f)
            if base in SEARCH_PLACES:
                self.searches.setdefault(base, []).append(f)
                continue
            if isinstance(f, BranchFilter):
                # an `or` list of one column's values reads `A or B` (funders, sources)
                cols = {lf.column_id for lf in _leaves(f) if isinstance(lf, LeafFilter)}
                if (f.join == "or" and not f.is_negated and len(cols) == 1
                        and all(isinstance(lf, LeafFilter) and lf.operator == "is"
                                and not lf.is_negated for lf in f.filters)):
                    col = cols.pop()
                    if col in ("funders.id", "primary_location.source.id",
                               "authorships.institutions.lineage", "authorships.countries"):
                        links = " or ".join(_link(lf.value, col, r) for lf in f.filters)
                        self._slot_for(col, links, thing)
                        continue
                self.where.append(f)
                continue
            if not isinstance(f, LeafFilter) or f.is_negated:
                self.where.append(f)
                continue
            col, val, op = f.column_id, f.value, f.operator
            if col in ADJECTIVES and val is True and op == "is":
                self.adjectives.append(ADJECTIVES[col])
            elif col == "type" and op == "is" and val in TYPE_NOUNS and self.type_noun == "works":
                self.type_noun = TYPE_NOUNS[val]
            elif col == "publication_year" and isinstance(val, int):
                key = {"is": "=", ">=": ">=", "<=": "<=", "<": "<", ">": ">="}.get(op)
                if key is None:
                    self.where.append(f)
                else:
                    self.years[key] = val + 1 if op == ">" else val
            elif col in ("from_publication_date", "to_publication_date") and op == "is":
                self.dates[">=" if col.startswith("from") else "<="] = val
            elif op == "in collection":
                if col == "referenced_works":
                    self._add("citing", f"citing works in the collection {_link(val, col, r)}")
                else:
                    self._add("in", f"in the collection {_link(val, col, r)}")
            elif op != "is" or isinstance(val, OQO):
                self.where.append(f)
            elif col == "authorships.author.id":
                self.authors.append(val)
            else:
                self._slot_for(col, _link(val, col, r), thing)

    def _slot_for(self, col, link, thing):
        if col == "authorships.institutions.lineage":
            self._add("from", f"co-authored with {link}" if thing == "institutions" else f"from {link}")
        elif col == "authorships.countries":
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
            words.append(_possessive(_link(self.star.value, self.star.column_id, r)))
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
            words.append("co-authored by " + _and_list(
                [_link(a, "authorships.author.id", r) for a in self.authors]))
        words += self.parts.get("role", [])
        for slot in ("in", "published", "funded", "license"):
            words += self.parts.get(slot, [])
        if self.where:
            words.append("where " + _where_text(self.where, r))
        return " ".join(words)

    def _has_conditions(self, keep_time=True) -> bool:
        return bool(self.star or self.adjectives or self.searches or self.parts or self.where
                    or self.authors or (keep_time and (self.years or self.dates)))


class _Leftover(Exception):
    pass


def _works(rows, resolver=None, possessive=True, thing=None) -> _Works:
    """Build the slots; a column with no phrase goes to `where`."""
    w = _Works.__new__(_Works)
    w.resolver = resolver
    w.star = None
    w.adjectives, w.type_noun, w.years, w.dates = [], "works", {}, {}
    w.searches, w.parts, w.where, w.authors = {}, {}, [], []
    w.year_dim = False
    singles = [f for f in rows if isinstance(f, LeafFilter) and not f.is_negated
               and f.operator == "is" and f.column_id in STAR_COLUMNS and isinstance(f.value, str)]
    if possessive and len(singles) == 1 and not (
            singles[0].column_id == "authorships.author.id"
            and any(isinstance(f, LeafFilter) and f.column_id == "corresponding_author_ids"
                    for f in rows) and False):
        w.star = singles[0]
    for f in rows:
        if f is w.star:
            continue
        try:
            w._read([f], possessive=False, thing=thing)
        except _Leftover:
            w.where.append(f)
    return w


# ---------------------------------------------------------------------------
# Measures
# ---------------------------------------------------------------------------
def _measure_name(m: Measure) -> str:
    key = (m.measure, m.column_id)
    if key in MEASURE_NAMES:
        return MEASURE_NAMES[key]
    from query_translation import oql_lang as L
    if m.measure == "value":
        return L.own_field_word(m.column_id) or L._oql_field(m.column_id)[0]
    if m.measure == "percent":
        return f"percent {L._oql_field(m.column_id)[0]}"
    if m.measure in ("sum",):
        return f"sum of {L._oql_field(m.column_id)[0]}"
    return f"{m.measure} {L._oql_field(m.column_id)[0]}"


def _measure_key(m: Measure) -> str:
    return m.key


def _show(measures: List[Measure]) -> str:
    return "Show " + _and_list([_measure_name(m) for m in measures]) + "."


# ---------------------------------------------------------------------------
# The things phrase (rank, and lists of things)
# ---------------------------------------------------------------------------
def _thing_parts(where, noun: str, resolver=None) -> Tuple[str, List[str], List, Optional[MeasureFilter]]:
    """(noun, phrases, leftovers, count filter) from a group's `where` tree."""
    parts: List[str] = []
    left: List = []
    count = None
    for f in (_and_items(where) if where is not None else []):
        if isinstance(f, AffiliationFilter) and not f.is_negated:
            parts.append(_affiliation_text(f, resolver))
        elif isinstance(f, MeasureFilter) and f.measure == "count" and not f.is_negated \
                and f.operator in COMPARATOR_WORDS:
            count = f
        elif isinstance(f, LeafFilter) and f.column_id == "type" and not f.is_negated \
                and (noun, f.value) in THING_TYPE_NOUNS:
            noun = THING_TYPE_NOUNS[(noun, f.value)]
        elif isinstance(f, LeafFilter) and f.column_id == "country_code" and not f.is_negated:
            parts.append(f"in {_link(f.value, 'authorships.countries', resolver)}")
        elif isinstance(f, LeafFilter) and f.column_id in OWN_FIELDS and f.operator in ABOVE_WORDS \
                and not f.is_negated:
            parts.append(f"with {OWN_FIELDS[f.column_id][0]} {ABOVE_WORDS[f.operator]} {_number(f.value)}")
        else:
            left.append(f)
    return noun, parts, left, count


def _and_items(node) -> List:
    if isinstance(node, BranchFilter) and node.join == "and" and not node.is_negated:
        out = []
        for f in node.filters:
            out += _and_items(f)
        return out
    return [node]


def _affiliation_text(f: AffiliationFilter, resolver=None) -> str:
    country = f.column_id.endswith("country_code")
    link = _link(f.value, "authorships.countries" if country else "authorships.institutions.lineage",
                 resolver)
    head = f"in {link}" if country else f"at {link}"
    if f.since is not None and f.through is not None:
        years = f" from {f.since}–{f.through}"
    elif f.since is not None:
        years = f" since {f.since}"
    elif f.through is not None:
        years = f" through {f.through}"
    else:
        head = "ever " + head
        years = ""
    extra = f" in {f.min_years}+ years" if f.min_years else ""
    return head + years + extra


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
    from query_translation import oql_lang as L
    word = L._oql_field(s.column_id)[0]
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
    return f"get the {_and_list(names)} {join} {w.text()}"


def _things_list(oqo, resolver):
    noun = oqo.get_rows
    parts, left = [], []
    for f in oqo.filter_rows:
        if isinstance(f, AffiliationFilter) and not f.is_negated:
            parts.append(_affiliation_text(f, resolver))
        elif isinstance(f, LeafFilter) and not f.is_negated and f.column_id in (
                "subfield.id", "field.id", "domain.id") and f.operator == "is":
            key = {"subfield.id": "the subfield", "field.id": "the field",
                   "domain.id": "the domain"}[f.column_id]
            parts.append(f"in {key} {_link(f.value, f.column_id, resolver)}")
        elif isinstance(f, LeafFilter) and not f.is_negated and f.column_id == "country_code" \
                and f.operator == "is":
            parts.append(f"in {_link(f.value, 'authorships.countries', resolver)}")
        else:
            left.append(f)
    sort = oqo.sort_by[0] if oqo.sort_by else None
    only = []
    if sort is not None and sort.column_id in OWN_FIELDS:
        # rank by an own field; a threshold on that field becomes `Only ...`
        rest = []
        for f in left:
            if isinstance(f, LeafFilter) and f.column_id == sort.column_id and f.operator in ABOVE_WORDS:
                only.append(f)
            else:
                rest.append(f)
        left = rest
    for f in list(left):
        if isinstance(f, LeafFilter) and f.column_id in OWN_FIELDS and f.operator in ABOVE_WORDS \
                and not f.is_negated:
            parts.append(f"with {OWN_FIELDS[f.column_id][0]} {ABOVE_WORDS[f.operator]} {_number(f.value)}")
            left.remove(f)
    if left:
        parts.append("where " + _where_text(left, resolver))
    phrase = " ".join([noun] + parts)
    if sort is not None and sort.column_id in OWN_FIELDS:
        text = f"rank {phrase} by {OWN_FIELDS[sort.column_id][1]}"
        if sort.direction == "asc":
            text += ", lowest first"
        for f in only:
            text += (f". Only {noun} with {OWN_FIELDS[f.column_id][0]} "
                     f"{ABOVE_WORDS[f.operator]} {_number(f.value)}.")
        return text
    return "get " + phrase + _order_text(oqo.sort_by)


def _rank(oqo, resolver):
    g = oqo.group_by[0]
    noun = THING_NOUNS[g.column_id]
    noun, parts, left, count = _thing_parts(g.where, noun, resolver)
    if left:
        raise NotCore("a things filter with no phrase")
    w = _works(oqo.filter_rows, resolver, possessive=False, thing=THING_NOUNS[g.column_id])
    works_text = w.text()
    if count is not None:
        n = count.value + 1 if count.operator == ">" and False else count.value
        parts.append(f"with {COMPARATOR_WORDS[count.operator]} {_number(n)} {works_text}")
    measures = list(oqo.calculate) or [Measure("count")]
    sort = oqo.sort_by[0] if oqo.sort_by else None
    ranked = measures[0]
    if sort is not None:
        hit = [m for m in measures if m.key == sort.column_id]
        if hit:
            ranked = hit[0]
    rest = [m for m in measures if m is not ranked]
    name = _measure_name(ranked)
    if count is not None and name != "count of works":
        by = name
    elif name == "count of works":
        by = "count of " + works_text
    elif works_text == "works":
        by = name
    else:
        by = f"{name} {MEASURE_JOIN.get(name, 'of')} {works_text}"
    text = f"rank {' '.join([noun] + parts)} by {by}"
    if sort is not None and sort.direction == "asc":
        text += ", lowest first"
    if rest:
        text += ". " + _show(rest)
    return text


def _breakdown(oqo, resolver):
    if len(oqo.group_by) > 2:
        raise NotCore("three dimensions")
    year_dim = any(g.column_id == "publication_year" for g in oqo.group_by)
    w = _works(oqo.filter_rows, resolver)
    dims = sorted(oqo.group_by, key=lambda g: 0 if g.column_id == "publication_year" else 1)
    texts = []
    for g in dims:
        if g.where is not None or g.column_id not in DIMS:
            raise NotCore("a dimension with no word")
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
