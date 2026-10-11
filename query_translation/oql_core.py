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

# negative yes/no words before the noun (cow paths, writing test 2026-10-11)
NEG_ADJECTIVES = {"is_retracted": "non-retracted", "open_access.is_oa": "closed access"}

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
for _col, _adj in ADJECTIVES.items():
    MEASURE_NAMES.setdefault(("percent", _col), f"percent {_adj}")
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
            if isinstance(f, LeafFilter) and f.is_negated and f.value is True \
                    and f.column_id in NEG_ADJECTIVES and f.operator == "is":
                self.adjectives.append(NEG_ADJECTIVES[f.column_id])
                continue
            if not isinstance(f, LeafFilter) or f.is_negated:
                self.where.append(f)
                continue
            col, val, op = f.column_id, f.value, f.operator
            if col in NEG_ADJECTIVES and val is False and op == "is":
                self.adjectives.append(NEG_ADJECTIVES[col])
            elif col in ADJECTIVES and val is True and op == "is":
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
        if isinstance(f, LeafFilter) and f.column_id == "type" and not f.is_negated \
                and (noun, f.value) in THING_TYPE_NOUNS and noun == oqo.get_rows:
            noun = THING_TYPE_NOUNS[(noun, f.value)]
        elif isinstance(f, AffiliationFilter) and not f.is_negated:
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
    if count is not None and name == "count of works":
        text = f"rank {' '.join([noun] + parts)}"    # ranked by that count
        if sort is not None and sort.direction == "asc":
            text += ", lowest first"
        return text + (". " + _show(rest) if rest else "")
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
        for _ in range(3):
            s = re.sub(r"⟦Q(\d+)⟧", lambda m: self.chunks[int(m.group(1))], s)
        return re.sub(r"⟦L(\d+)⟧", lambda m: "[%s](%s)" % self.links[int(m.group(1))], s)

    def link_id(self, tok: str) -> Optional[str]:
        m = re.fullmatch(r"⟦L(\d+)⟧(?:'s)?", tok)
        return self.links[int(m.group(1))][1] if m else None


def _kind_of(id_: str) -> Optional[str]:
    """The entity an ID's shape names: I.. institution, A.. author, S.. source, ..."""
    if id_.startswith("col_"):
        return "collection"
    m = re.fullmatch(r"([A-Za-z])(\d+)", id_)
    if m:
        return {"I": "institution", "A": "author", "S": "source", "F": "funder", "P": "publisher",
                "T": "topic", "W": "work"}.get(m.group(1).upper())
    if re.fullmatch(r"[A-Z]{2}", id_):
        return "country"
    if re.fullmatch(r"Q\d+", id_):
        return "continent"
    return None


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
        self.w = s.split()
        self.i = 0

    def peek(self, n=0) -> Optional[str]:
        j = self.i + n
        return self.w[j] if j < len(self.w) else None

    def at(self, *words) -> bool:
        return all(self.peek(k) is not None and self.peek(k).lower() == w.lower()
                   for k, w in enumerate(words))

    def take(self, n=1) -> List[str]:
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
        if sep == "and" and (ws.peek() or "").endswith(",") is False and ws.at(",") is False:
            pass
        break
    return ids


def _any_of(col: str, ids: List[str]):
    leaves = [LeafFilter(col, i) for i in ids]
    return leaves[0] if len(leaves) == 1 else BranchFilter(join="or", filters=leaves)


_SEARCH_FIELD_FOR = {"the title": "title", "the abstract": "abstract", "the full text": "full text",
                     "the title or abstract": "title-abstract"}


def _parse_works(t: _Text, s: str, collection_type: Optional[Callable] = None,
                 thing: Optional[str] = None) -> List:
    """A works phrase -> its filters (an AND list)."""
    ws = _Words(t, s)
    rows: List = []
    # possessive star
    tok = ws.peek() or ""
    if tok.endswith("'s") and t.link_id(tok):
        id_ = t.link_id(tok)
        kind = _kind_of(id_)
        col = {"institution": "authorships.institutions.lineage", "country": "authorships.countries",
               "author": "authorships.author.id"}.get(kind)
        if col is None:
            raise NotCore(f"a possessive on {id_}")
        rows.append(LeafFilter(col, id_))
        ws.take()
    # adjectives
    while True:
        hit = None
        for col, adj in NEG_ADJECTIVES.items():
            if ws.at(*adj.split()):
                rows.append(LeafFilter(col, False))
                ws.take(len(adj.split()))
                hit = True
                break
        if hit:
            continue
        for col, adj in ADJECTIVES.items():
            parts = adj.split()
            if ws.at(*parts):
                hit = (col, len(parts))
                break
        if not hit:
            break
        rows.append(LeafFilter(hit[0], True))
        ws.take(hit[1])
    # the type noun
    if ws.at("all", "works"):
        ws.take(2)
    else:
        if ws.at("all"):
            ws.take()
        for noun in sorted(NOUN_TYPES, key=lambda n: -len(n.split())):
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
            for words in sorted(_SEARCH_FIELD_FOR, key=lambda w: -len(w.split())):
                if ws.at("in", *words.split()):
                    place = words
                    ws.take(1 + len(words.split()))
                    break
            if place is None:
                ws.i = save
                raise NotCore("`with` needs `in the title` (or abstract, full text)")
            rows += _old_filters("works", f"{_SEARCH_FIELD_FOR[place]} has {t.restore(s_tok)}")
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
            while t.link_id(ws.peek() or ""):
                ids.append(t.link_id(ws.take()[0].rstrip(",")))
                if ws.at("and") or ws.at(","):
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
            col = {"institution": "authorships.institutions.lineage",
                   "country": "authorships.countries",
                   "continent": "authorships.institutions.continent"}.get(kind)
            if col is None:
                raise NotCore(f"`from` {ids[0]}")
            rows.append(_any_of(col, ids))
            continue
        if ws.at("by") and t.link_id(ws.peek(1) or ""):
            ws.take()
            rows.append(_any_of("authorships.author.id", _links_list(ws)))
            continue
        if ws.at("in", "the", "collection"):
            ws.take(3)
            cid = t.link_id(ws.take()[0])
            ctype = collection_type(cid) if collection_type else "works"
            col = {"institutions": "authorships.institutions.lineage", "authors": "authorships.author.id",
                   "sources": "primary_location.source.id", "works": "id",
                   "funders": "funders.id", "topics": "primary_topic.id"}.get(ctype or "works", "id")
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
            if _kind_of(ids[0]) != "source":
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
    names = [n.strip() for n in re.split(r",\s*|\s+and\s+", s) if n.strip()]
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


def core_first(text: str) -> bool:
    """Sentences only core v3 has: try its parser before today's."""
    low = " ".join(text.split()).lower()
    return low.startswith(("rank ", "break down ", "get the "))


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
    if first in NOUN_THINGS or first in NOUN_THING_TYPES or first in THING_ENTITIES:
        oqo = _parse_things_list(t, body)
    else:
        oqo = OQO(get_rows="works", filter_rows=_parse_works(t, body, collection_type))
    oqo.sort_by = sort
    return oqo


def _parse_number(t, s, collection_type):
    m = re.match(r"(.+?) (of|for) (.+)$", s)
    if not m:
        raise NotCore("`get the <measure> of <works>`")
    # the measures end where a works phrase begins
    head, rest = s, None
    for mm in re.finditer(r" (of|for) ", s):
        cand = s[: mm.start()]
        try:
            measures = _parse_measures(t, cand)
        except NotCore:
            continue
        rest = s[mm.end():]
        head = cand
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
        if ws.at("ever", "at") or ws.at("at"):
            ever = ws.at("ever")
            ws.take(2 if ever else 1)
            id_ = t.link_id(ws.take()[0])
            since = through = None
            yrs = None if ever else _years_from(ws, "years")
            for y in yrs or []:
                if y.operator == ">=":
                    since = y.value
                elif y.operator == "<=":
                    through = y.value
                elif y.operator == "is":
                    since = through = y.value
            items.append(AffiliationFilter("affiliations.institution.lineage", id_, since, through))
            continue
        if ws.at("in") and t.link_id(ws.peek(1) or "") and _kind_of(t.link_id(ws.peek(1))) == "country":
            ws.take()
            id_ = t.link_id(ws.take()[0])
            if noun == "authors":
                yrs = _years_from(ws, "years") or []
                since = next((y.value for y in yrs if y.operator == ">="), None)
                items.append(AffiliationFilter("affiliations.institution.country_code", id_, since, None))
            else:
                items.append(LeafFilter("country_code", id_))
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
            if word not in WORD_COMPARATORS:
                raise NotCore(f"`with {word}`")
            n = int(ws.take()[0].replace(",", ""))
            items.append(("count", WORD_COMPARATORS[word], n, ws.rest()))
            ws.i = len(ws.w)
            continue
        if ws.at("with"):
            m = re.match(r"with (an?) ([\w\-]+(?: count)?) (above|at least|below|at most) ([\d,.]+)",
                         ws.rest())
            if m and m.group(2) in OWN_FIELD_BY_WORD:
                op = {v: k for k, v in ABOVE_WORDS.items()}[m.group(3)]
                items.append(LeafFilter(OWN_FIELD_BY_WORD[m.group(2)], _num(m.group(4)), op))
                ws.take(len(m.group(0).split()))
                continue
        raise NotCore(f"unexpected {ws.peek()!r} in a things phrase")
    return noun, typ, items


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
    entity = THING_ENTITIES.get(noun)
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
        col = {"the subfield": "subfield.id", "the field": "field.id", "the domain": "domain.id"}[m.group(1)]
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
    noun = things.split()[0].lower()
    # rank by an own field: a sorted list of things
    if measure in OWN_FIELD_BY_WORD:
        oqo = _parse_things_list(t, things)
        col = OWN_FIELD_BY_WORD[measure]
        for o in only:
            mm = re.match(r"\w+ with (an?) ([\w\-]+(?: count)?) (above|at least|below|at most) ([\d,.]+)$", o)
            if not mm:
                raise NotCore("`Only <things> with an <field> above N`")
            op = {v: k for k, v in ABOVE_WORDS.items()}[mm.group(3)]
            oqo.filter_rows.append(LeafFilter(OWN_FIELD_BY_WORD[mm.group(2)], _num(mm.group(4)), op))
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
    ranked = None
    for name in sorted(NAME_MEASURES, key=len, reverse=True):
        if measure == name or measure.startswith(name + " "):
            ranked = name
            break
    if measure == "count of works":
        ranked, phrase = "count of works", ""
    elif measure.startswith("count of "):
        ranked = "count of works"
        phrase = measure[len("count of "):]
    elif ranked is None:
        raise NotCore(f"unknown measure in {measure!r}")
    else:
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
        if any(nxt == w or nxt.startswith(w + " ") for w in DIM_COLUMNS):
            cut = mm
            break
    if cut is None:
        raise NotCore("`break down <works> by <dimension>`")
    phrase, dims_text = s[: cut.start()], s[cut.end():]
    rows = _parse_works(t, phrase, collection_type)
    groups: List[GroupBy] = []
    for part in re.split(r"\s+and\s+(?=(?:%s)\b)" % "|".join(
            re.escape(w) for w in sorted(DIM_COLUMNS, key=len, reverse=True)), dims_text):
        word = next((w for w in sorted(DIM_COLUMNS, key=len, reverse=True)
                     if part == w or part.startswith(w + " ")), None)
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
    return OQO(get_rows="works", filter_rows=rows, group_by=groups,
               calculate=[Measure("count"), Measure("percent_of_those")])


# ===========================================================================
# The automatic baseline (Jason, 2026-10-11 17:45 CT)
# ===========================================================================
BASELINE_COLUMNS = ("authorships.institutions.lineage", "authorships.countries",
                    "authorships.author.id", "primary_location.source.id", "funders.id")


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
    return replace(oqo, filter_rows=rest, cursor=None,
                   calculate=[Measure("count"), Measure("percent_of_those")]), star
