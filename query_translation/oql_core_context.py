"""Editor autocomplete for OQL core v3, the get-only English surface (oxjob #1597).

`/parse-context` answers "what fits at the cursor?" for the IDE-style editor. Today's
resolver (`oql_context`) knows only the key-value grammar; this module answers for core v3
statements (`get works about kelp since 2020, most cited first`, `get the count of works
by country`, `get authors at [UBC](I141945490)`), and `oql_context.parse_context` routes
here when `is_core(q)` says the statement is one.

One grammar, one vocabulary (Jason, 2026-10-09): every suggestion comes from
`oql_core`'s own tables (TYPE_NOUNS, ADJECTIVES, DIMS, THING_NOUNS, MEASURE_NAMES,
ORDER_PHRASES, OWN_FIELDS, YEAR_OPS, LINK_SLOTS, ...) and its own order-words functions,
and `tests/oql/test_core_context.py` checks that every offered phrase parses with
`oql_core.parse_core`. A `where` tail is handed to today's resolver on the equivalent
`get <entity> where <tail>`, with its offsets shifted back.

The walker below mirrors the core parser's reading order (`_parse_works`, `_parse_table`,
`_parse_things`), tolerantly: it reads the words before the cursor and stops where the
cursor is, reporting the slot, the words already typed of a phrase (the prefix) and what
fits there. Pure Python, no ES or DB; it runs on every keystroke.
"""
from __future__ import annotations

import datetime
import functools
import re
from typing import Any, Dict, List, Optional, Tuple

from query_translation import oql_core as C
from query_translation.oql_context import _DIRECTIVE_WORDS
from query_translation.oql_lang import ENTITY_TYPES, THING_VERBS, entity_type_for_column
from query_translation.oqo import SortBy

# ---------------------------------------------------------------------------
# Routing: is this a core v3 statement?
# ---------------------------------------------------------------------------
_GET = re.compile(r"\s*get(?:\s|$)", re.I)
# `get works where ...`, `get works group by ...`, `get works sample 10`: today's directives
_OLD_GET = re.compile(r"\s*get\s+(?:%s)\s+(?:%s)\b" % (
    "|".join(re.escape(e) for e in sorted(ENTITY_TYPES, key=len, reverse=True)),
    "|".join(sorted(_DIRECTIVE_WORDS))), re.I)
# the general form's steps and thing verbs (`get authors who published works where ...`)
_PIPELINE = re.compile(r";|\b(?:then|finally)\s*,|\b(?:%s)\b" % "|".join(
    sorted({v.replace(" ", r"\s+") for v in THING_VERBS.values() if " " in v})), re.I)


def is_core(q: str) -> bool:
    """A cheap, safe check: True only for a statement core v3 reads (or the word `get`
    being typed). `get works where ...` and every general-form statement stay on today's
    resolver, byte for byte."""
    s = q.strip()
    if not s:
        return False
    if not _GET.match(q):
        return "get".startswith(s.lower())
    return not (_OLD_GET.match(q) or _PIPELINE.search(q))


def clamp(q: str, pos: Optional[int]) -> int:
    """The cursor as a code-point offset inside `q` (the end when not given)."""
    return len(q) if pos is None else max(0, min(pos, len(q)))


# ---------------------------------------------------------------------------
# Vocabulary: value, kind, detail (<= 50 chars), doc (plain English, an example)
# ---------------------------------------------------------------------------
def _e(value: str, kind: str, detail: str, doc: str, insert: Optional[str] = None,
       cursor: Optional[int] = None) -> Dict[str, Any]:
    d = {"value": value, "kind": kind, "detail": detail, "doc": doc}
    if insert is not None:
        d["insert"] = insert
    if cursor is not None:
        d["cursor"] = cursor
    return d


def _with(entry: Dict[str, Any], **kw) -> Dict[str, Any]:
    d = dict(entry)
    d.update(kw)
    return d


K = {}   # keyword entries by value (one slot's meaning; context variants are built below)


def _kw(value, detail, doc, kind="keyword", **kw):
    K[value] = _e(value, kind, detail, doc, **kw)
    return K[value]


_kw("get", "starts every statement", "Every statement starts with get: `get works about kelp`.")
_kw("the", "numbers about works: a count, a mean ...",
    "Starts a table of numbers: `get the count of works about kelp by country`.")
_kw("of", "the works the numbers are about",
    "Joins the numbers to their works: `get the count of works since 2020`.")
_kw("to", "the works the citations go to",
    "`sum of citations` takes to: `get the sum of citations to works about oleogel* by author`.")
_kw("for", "the works the fees were paid for",
    "`sum of APCs paid` takes for: `get the sum of APCs paid for works funded by "
    "[Wellcome Trust](F4320311904) by publisher`.")
_kw("and", "add another one",
    "Joins numbers or splits: `get the count and mean FWCI of works by year and country`.")
_kw("or", "either of these",
    "Either one: `get works funded by [Russian Science Foundation](F4320324099) or "
    "[Russian Foundation for Basic Research](F4320321079)`.")
_kw("'s", "the works of this institution, country or person",
    "A possessive names whose works: `get [University of Kansas](I146416000)'s works`.")
_kw("about", "search titles, abstracts and keywords",
    "Searches title, abstract and keywords: `get works about (coral AND reef*)`. One word or "
    "one quoted phrase needs no parentheses: `about kelp`.", insert="about ()", cursor=7)
_kw("since", "published in or after a year", "`get works about kelp since 2020`.")
_kw("from", "a place (institution, country) or a year",
    "A place: `get works from [Kenya](KE)`. A year or a range: `from 2022`, `from 2018–2025`.")
_kw("before", "published before a year", "`get works about kelp before 2010`.")
_kw("through", "published in or before a year", "`get works about kelp from 2015 through 2020`.")
_kw("by", "works by this author",
    "`get works by [Jennifer A. Doudna](A5067184382)`. Two or more people together: "
    "`co-authored by`.")
_kw("in", "in this journal or other source",
    "`get works in [Heliyon](S2898612692)`. Classifications name their kind: "
    "`in the topic`, `in the field`, `in SDG`.")
_kw("co-authored with", "with an author at this institution",
    "`get the count of works co-authored with [Kiel University](I32021983) by company`.")
_kw("co-authored by", "two or more people's works together",
    "`get works co-authored by [Jennifer A. Doudna](A5067184382) and "
    "[Emmanuelle Charpentier](A5074743574)`.")
_kw("citing", "works that cite this work",
    "`get works citing [Progress in battery thermal management](W4399795944)`.")
_kw("citing works in the collection", "works citing works in your collection",
    "`get the count of works citing works in the collection [JMIR articles](col_jmir) "
    "by institution`.")
_kw("published by", "in this publisher's journals",
    "`get works published by [Elsevier BV](P4310320990)`.")
_kw("funded by", "funded by this funder",
    "`get works funded by [Wellcome Trust](F4320311904)`. Several: `funded by [A](F1) or [B](F2)`.")
_kw("under the … license", "works under this license",
    "`get works under the [CC BY](cc-by) license`.", insert="under the  license", cursor=10)
_kw("where", "any other field, as field is value",
    "Conditions the phrases can't say go last: `get works about kelp where language is "
    "[English](en)`.")
_kw("with … as corresponding author", "this person is the corresponding author",
    "`get works with [Jennifer A. Doudna](A5067184382) as corresponding author`.",
    insert="with  as corresponding author", cursor=5)
_kw("as corresponding author", "this person is the corresponding author",
    "`get works with [Jennifer A. Doudna](A5067184382) as corresponding author`.")
_kw("license", "ends under the … license", "`get works under the [CC BY](cc-by) license`.")
_kw("both", "works with every one of these places",
    "`get works from both [University of Oxford](I40120149) and [University of Cambridge]"
    "(I241749)`.")
_kw("all of", "works with all of three or more places",
    "`get works from all of [A](I1), [B](I2), and [C](I3)`.")
_kw("the collection", "the members of one of your collections",
    "`get works in the collection [Catalan institutions](col_cat)`.")
_kw("works in the collection", "works citing works in your collection",
    "`get works citing works in the collection [JMIR articles](col_jmir)`.")
_kw("in the collection", "the members of one of your collections",
    "`get the count of works in the collection [Catalan institutions](col_cat) by year`.")
# `in <key> [X]`: classifications name their kind (oql_core.IN_KEYS)
_IN_KEY_DOC = {"SDG": ("in this Sustainable Development Goal",
                       "`get works in SDG [Climate action](13)`."),
               "the topic": ("in this primary topic",
                             "`get works in the topic [Concrete and Cement Materials Research]"
                             "(T10033)`."),
               "the subfield": ("in this subfield", "`get works in the subfield "
                                "[Artificial Intelligence](1702)`."),
               "the field": ("in this field", "`get works from 2022 in the field "
                             "[Computer Science](17)`."),
               "the domain": ("in this domain", "`get works in the domain [Physical Sciences](3)`.")}
for _key in C.IN_KEYS.values():
    _d, _doc = _IN_KEY_DOC.get(_key, (f"in this {_key.replace('the ', '')}",
                                      f"`get works in {_key} [X](1)`."))
    _kw("in " + _key, _d, _doc)
    _kw(_key, _d, _doc)
for _key in C.THING_IN_KEYS.values():
    if _key not in K:
        _kw(_key, f"in this {_key.replace('the ', '')}", f"`get topics in {_key} [X](1)`.")

# with <search> in <place> (oql_core.SEARCH_PLACES)
_PLACE_DOC = {"the title": "the title only", "the abstract": "the abstract only",
              "the full text": "the full text only", "the title or abstract": "title or abstract"}
PLACES = []
WITH_SEARCH = []
for _place in C.SEARCH_FIELD_FOR:
    _w = _PLACE_DOC.get(_place, _place)
    PLACES.append(_kw("in " + _place, f"search {_w}",
                      f"`get works with conjugal in {_place}`.", kind="place"))
    WITH_SEARCH.append(_kw(f"with … in {_place}", f"search {_w}",
                           f"`get works with (\"smart grid\" AND security) in {_place}`.",
                           insert=f"with () in {_place}", cursor=6))

# author records and things' own conditions
_kw("at", "their record lists this institution",
    "An author's record: `get authors at [University of British Columbia](I141945490)`, "
    "`by author at [University of Kansas](I146416000)`.")
_kw("in 2+ years", "listed there in two or more years",
    "`get authors at [University of British Columbia](I141945490) in 2+ years since 2022`.")
_kw("except", "leave these out",
    "`get the count of works from [Kenya](KE) by country except [Kenya](KE)`. Several: "
    "`except ([A](I1), [B](I2))`.")
_THING_IN = _e("in", "keyword", "in this country or continent",
               "Things by their own place: `get institutions in [Brazil](BR)`, "
               "`by institution in [Sweden](SE)`.")
_VALUES_IN = _e("in (…)", "keyword", "only these groups",
                "A list of rows: `by country in ([United States](US), [China](CN))`.",
                insert="in ()", cursor=4)
_PAREN = _e("(…)", "keyword", "a list of values in parentheses",
            "`by country in ([United States](US), [China](CN))`.", insert="()", cursor=1)
_kw("ever at", "their record lists this institution",
    "`get authors ever at [University of Kansas](I146416000)`.")
_kw("other than", "leave these out", "`get institutions other than [ETH Zurich](I35440088)`.")

# own-field thresholds: `with an h-index above 50` (oql_core.OWN_FIELDS x ABOVE_WORDS)
THRESHOLDS = []
for _col, (_with_word, _word) in C.OWN_FIELDS.items():      # ("an h-index", "h-index")
    for _op, _aw in C.ABOVE_WORDS.items():
        THRESHOLDS.append(_kw(f"with {_with_word} {_aw}", f"their own {_word} {_aw} a number",
                              f"`get authors with {_with_word} {_aw} 50`."))
_SHOWN_THRESHOLDS = [x for x in THRESHOLDS if x["value"].endswith(" above")]
# count floors: `Only institutions with at least 10 works about kelp.` (COMPARATOR_WORDS)
COMPARATORS = [_kw(f"with {w}", f"groups with {w} N works",
                   f"`Only institutions with {w} 10 works about kelp.`")
               for w in C.COMPARATOR_WORDS.values()]

SENTENCE = {
    "Show": _e("Show", "sentence", "add a thing's own fields",
               "A thing's own fields, after the main sentence: `get the count of works about kelp "
               "by author. Show h-index.`"),
    "Only": _e("Only", "sentence", "a count floor on the groups",
               "Its own sentence: `Only institutions with at least 10 works about kelp.`"),
}

# -- nouns -------------------------------------------------------------------
NOUNS = {"works": _e("works", "noun", "every type of work",
                     "`get works about kelp`. `works` counts every type, datasets too."),
         "all works": _e("all works", "noun", "every work, no conditions",
                         "`get the count and share of all works by SDG`.")}
for _noun in C.NOUN_TYPES:
    NOUNS[_noun] = _e(_noun, "noun", f"only {_noun}",
                      f"Works of one type: `get {_noun} about kelp since 2020`.")
_THING_DOC = {
    "authors": "`get authors at [University of British Columbia](I141945490) with an h-index "
               "above 50, highest h-index first`.",
    "institutions": "`get institutions in [Brazil](BR), most cited first`.",
    "countries": "`get countries in [Africa](Q15), most cited first`.",
    "sources": "`get sources with an h-index above 100, highest h-index first`.",
    "topics": "`get topics in the subfield [Artificial Intelligence](1702)`.",
    "fields": "`get fields in the domain [Physical Sciences](3)`.",
    "subfields": "`get subfields in the field [Computer Science](17)`.",
    "funders": "`get funders, most cited first`.",
    "publishers": "`get publishers, highest works count first`.",
    "companies": "`get companies in [Germany](DE), most cited first`.",
    "journals": "`get journals with an h-index above 100`.",
    "repositories": "`get repositories, highest works count first`.",
}
THINGS = {}
for _noun in list(C.NOUN_THINGS) + list(C.NOUN_THING_TYPES):
    _base, _typ = C.NOUN_THING_TYPES.get(_noun, (_noun, None))
    THINGS[_noun] = _e(_noun, "noun", f"a list of {_base} of type {_typ}" if _typ
                       else f"a list of {_noun}",
                       "Things by their own fields: " + _THING_DOC.get(_noun, f"`get {_noun}`."))

_ADJ_DOC = {"open access": ("free to read", "`get open access articles about kelp`."),
            "closed access": ("not free to read", "`get closed access works from 2020`."),
            "retracted": ("retracted works only",
                          "`get the count of retracted works from 2023 by journal`."),
            "non-retracted": ("leaves retracted works out", "`get non-retracted works about ivermectin`."),
            "top 1% cited": ("top 1% by citations for field and year",
                             "`get top 1% cited articles from [Kenya](KE)`."),
            "top 10% cited": ("top 10% by citations for field and year",
                              "`get the count of top 10% cited works by year`.")}
ADJECTIVES = {}
for _adj in list(C.ADJECTIVES.values()) + list(C.NEG_ADJECTIVES.values()):
    _d, _doc = _ADJ_DOC.get(_adj, (f"only {_adj} works", f"`get {_adj} works about kelp`."))
    ADJECTIVES[_adj] = _e(_adj, "adjective", _d, "A yes/no word before the noun: " + _doc)

# -- measures (oql_core.MEASURE_NAMES; `count` and `share` are their table names) --------
_MEASURE_DOC = {
    "count": ("how many works", "`get the count of works about kelp by country`."),
    "share": ("each row's slice of the whole",
              "Each row's part of the group one level up: `get the count and share of all works "
              "by SDG`."),
    "sum of citations": ("total citations to the works",
                         "Takes to: `get the sum of citations to works about oleogel* by author`."),
    "sum of APCs paid": ("estimated article fees paid (USD)",
                         "Takes for: `get the sum of APCs paid for works funded by [Wellcome "
                         "Trust](F4320311904) by publisher`."),
    "mean FWCI": ("average field-weighted citation impact",
                  "`get the count and mean FWCI of works since 2015 by country`."),
    "median FWCI": ("middle field-weighted citation impact",
                    "`get the median FWCI of works about kelp by country`."),
    "mean citations": ("average citations per work",
                       "`get the count and mean citations of works from 2022 in the field "
                       "[Computer Science](17)`."),
    "median citations": ("middle citation count", "`get the median citations of works by year`."),
    "h-index": ("a thing's own h-index",
                "Not a number of the works: `get the count of works about kelp by author. "
                "Show h-index.`"),
    "works count": ("a thing's own count of all its works",
                    "`get the count of works about kelp by institution. Show works count.`"),
}
MEASURES = {}
for _name in C.MEASURE_NAMES.values():
    _name = C.TABLE_NAMES.get(_name, _name)
    if _name.startswith("percent "):
        _rest = _name[len("percent "):]
        _d = f"share of works {_rest}" if _rest.startswith("with") else f"share of works that are {_rest}"
        _doc = f"`get the count and {_name} of works by year`."
    else:
        _d, _doc = _MEASURE_DOC.get(_name, (_name, f"`get the {_name} of works by year`."))
    MEASURES[_name] = _e(_name, "measure", _d, _doc)
# the long names the parser reads too: hover help, never offered
_HOVER_ONLY = [_with(MEASURES[short], value=long) for long, short in C.TABLE_NAMES.items()]
# a thing's own fields (h-index, works count) are `Show` and order words, not numbers
_OWN_NAMES = [n for n in MEASURES if C._measure_named(n).measure == "value"]
MAIN_MEASURES = [m for n, m in MEASURES.items() if n not in _OWN_NAMES]
SHOW_MEASURES = list(MEASURES.values())

# -- splits (oql_core.DIMS + THING_SINGULAR) ---------------------------------
_SPLIT_DOC = {"year": "`get the count of works about kelp by year since 2004`. The years follow "
                      "the word.",
              "author": "`get the count of works about kelp by author at [University of British "
                        "Columbia](I141945490)`.",
              "institution": "`get the count of works about kelp by institution in [Sweden](SE)`.",
              "country": "`get the count of works about \"quantum computing\" by country`.",
              "company": "`get the count of works co-authored with [Kiel University](I32021983) "
                         "by company`."}
_SPLIT_ORDER = ["year", "country", "institution", "author", "journal", "source", "publisher",
                "funder", "topic", "subfield", "field", "domain", "SDG", "type", "open access",
                "open access status", "language", "corresponding author", "company",
                "repository", "retracted"]
SPLITS = {}
for _w in sorted(C._SPLIT_WORDS, key=lambda w: (_SPLIT_ORDER.index(w) if w in _SPLIT_ORDER else 99, w)):
    SPLITS[_w] = _e(_w, "split", f"one row per {_w}",
                    _SPLIT_DOC.get(_w, f"`get the count of works about kelp by {_w}`."))

# -- orders ------------------------------------------------------------------
_ORDER_DOC = {
    "most cited first": ("highest citation count first", "`get works about kelp, most cited first`."),
    "least cited first": ("lowest citation count first", "`get works about kelp, least cited first`."),
    "newest first": ("latest first", "`get works about kelp, newest first`. In a table by year: "
                                     "latest year first."),
    "oldest first": ("earliest first", "`get works about kelp, oldest first`."),
    "best matches first": ("closest to the search first",
                           "The default with a search: `get works about kelp, best matches first`."),
    "highest FWCI first": ("highest field-weighted impact first",
                           "`get articles about CRISPR, highest FWCI first`."),
    "lowest FWCI first": ("lowest field-weighted impact first",
                          "`get articles about CRISPR, lowest FWCI first`."),
    "alphabetical by title": ("A to Z by title", "`get works about kelp, alphabetical by title`."),
    "reverse alphabetical by title": ("Z to A by title",
                                      "`get works about kelp, reverse alphabetical by title`."),
    C.AGE_ADJUSTED_WORDS: ("most cited for their age",
                           "The default with no search: citations weighed by year. With a search: "
                           "`get works about kelp, most cited (age-adjusted) first`."),
    "most works first": ("groups with the most works first",
                         "The default, except for years: `get the count of works by year, most "
                         "works first`."),
    "fewest works first": ("groups with the fewest works first",
                           "`get the count of works about kelp by country, fewest works first`."),
    "highest first": ("the highest number first",
                      "With one number: `get the mean FWCI of works about kelp by country, "
                      "highest first`."),
    "lowest first": ("the lowest number first",
                     "With one number: `get the mean FWCI of works about kelp by country, lowest "
                     "first`."),
}
ORDERS: Dict[str, Dict[str, Any]] = {}


def _order(value: str) -> Dict[str, Any]:
    if value not in ORDERS:
        d, doc = _ORDER_DOC.get(value, (None, None))
        if d is None:
            m = re.match(r"(highest|lowest|latest|earliest) (.+) first$", value)
            if m:
                d = f"{'largest' if m.group(1) in ('highest', 'latest') else 'smallest'} " \
                    f"{m.group(2)} at the top"
                doc = f"Order by a number: `get the count and {m.group(2)} of works by country, " \
                      f"{value}`." if m.group(2) in MEASURES else f"Order by a number: `..., {value}`."
            elif value.startswith(("alphabetical", "reverse alphabetical")):
                word = value.split(" by ", 1)[-1]
                d = ("Z to A" if value.startswith("reverse") else "A to Z") + f" by {word}"
                doc = f"Order the rows by name: `get the count of works by {word}, {value}`."
            else:
                d, doc = value, f"`..., {value}`."
        ORDERS[value] = _e(value, "order", d[:50], doc)
    return ORDERS[value]


LIST_ORDERS = [_order(p) for p in C.ORDER_PHRASES if p != "best matches first"]
LIST_ORDERS_SEARCH = LIST_ORDERS + [_order(C.AGE_ADJUSTED_WORDS)]


@functools.lru_cache(maxsize=None)
def _things_orders(entity: str) -> Tuple[Dict[str, Any], ...]:
    """A list of things' orders: the words the renderer writes for each own field."""
    words = (C._sort_words(entity, SortBy(col, d)) for col in C.OWN_FIELDS for d in ("desc", "asc"))
    return tuple(_order(w) for w in words if w)


def _after_comma(orders) -> List[Dict[str, Any]]:
    """Orders offered before their comma is typed insert it too: `, most cited first`."""
    return [_with(o, insert=", " + o["value"]) for o in orders]


# -- years -------------------------------------------------------------------
_YEAR_DETAIL = {"since": "published in {y} or later", "from": "published in {y}",
                "in": "published in {y}", "before": "published before {y}",
                "through": "published in {y} or earlier"}
_YEARISH = re.compile("|".join((C._DATE, C._YEAR, C._RANGE.pattern.rstrip("$"))))


def _year_entries(word: str) -> List[Dict[str, Any]]:
    y = datetime.date.today().year
    return [_year(word, str(v)) for v in (y - 1, y - 2, y - 6, y - 11)]


def _year(word: str, y: str) -> Dict[str, Any]:
    return _e(y, "year", _YEAR_DETAIL.get(word, "published in {y}").format(y=y),
              f"`get works about kelp {word} {y}`.")


# ---------------------------------------------------------------------------
# Slots
# ---------------------------------------------------------------------------
def _ptable(values) -> Dict[str, List[Tuple[Tuple[str, ...], str]]]:
    """Phrases to match by their first word, longest first: {word: [(words, value)]}."""
    out: Dict[str, List[Tuple[Tuple[str, ...], str]]] = {}
    for v in values:
        v = v["value"] if isinstance(v, dict) else v
        words = tuple(v.lower().split())
        out.setdefault(words[0], []).append((words, v))
    for phrases in out.values():
        phrases.sort(key=lambda x: -len(x[0]))
    return out


class _Slot:
    __slots__ = ("name", "options", "entities", "group", "group_entities", "bracket_entities",
                 "years", "table")

    def __init__(self, name, options=(), entities=(), group=None, group_entities=(),
                 bracket_entities=(), years=None, table=None):
        self.name = name
        self.options = list(options)
        self.entities = list(entities)
        self.group = group                    # what a ( ... ) here holds: "search" | "values"
        self.group_entities = list(group_entities)
        self.bracket_entities = list(bracket_entities)   # offered once `[` is typed
        self.years = years                    # a year word: year suggestions follow it
        self.table = table if table is not None else _ptable(
            o for o in self.options if o.get("kind") != "year")


def _ent(*cols: str) -> List[str]:
    """The `/autocomplete/<entity>` names for works columns (the registry's own mapping)."""
    return [e for e in (entity_type_for_column(c) for c in cols) if e]


_STAR_ENTITIES = _ent(*C.STAR_COLUMNS)
_FROM_ENTITIES = list(C.FROM_KINDS)
_WORK_NOUNS = [NOUNS["works"]] + [NOUNS[n] for n in C.NOUN_TYPES]
_HEAD_OPTS = [K["the"]] + _WORK_NOUNS + list(ADJECTIVES.values()) + list(THINGS.values())
_NOUN_OPTS = list(ADJECTIVES.values()) + _WORK_NOUNS
_NOUN_OPTS_TABLE = [NOUNS["all works"]] + _NOUN_OPTS
S_START = _Slot("head", [K["get"]])
S_HEAD = _Slot("head", _HEAD_OPTS, entities=_STAR_ENTITIES)
S_POSS = _Slot("noun", [K["'s"]])
S_NOUN = _Slot("noun", _NOUN_OPTS)
S_NOUN_TABLE = _Slot("noun", _NOUN_OPTS_TABLE, entities=_STAR_ENTITIES)
# choice slots: the alternatives a click on a written phrase offers
S_CHOICE_WORKS_NOUN = _Slot("noun", _WORK_NOUNS[:1] + [NOUNS["all works"]] + _WORK_NOUNS[1:])
S_CHOICE_THING_NOUN = _Slot("noun", list(THINGS.values()))
S_CHOICE_ADJ = _Slot("adjective", list(ADJECTIVES.values()))
S_MEASURE = _Slot("measure", MAIN_MEASURES)
S_MEASURE_SHOW = _Slot("measure", SHOW_MEASURES)
S_SPLIT = _Slot("split", list(SPLITS.values()), bracket_entities=["authors"])
S_PLACE = _Slot("place", PLACES)
S_SEARCH = _Slot("search-text", group="search", bracket_entities=["authors"])
S_ABOUT = _Slot("search-text", group="search")
S_NUMBER = _Slot("number")
S_YEAR = {w: _Slot("year", years=w) for w in C.YEAR_OPS}
S_LICENSE_WORD = _Slot("works-slot", [K["license"]])
S_CORRESPONDING_WORD = _Slot("works-slot", [K["as corresponding author"]])

_WS_HEAD = [K["about"], K["since"], K["from"], K["by"], K["in"], K["funded by"], K["published by"]]
_WS_TAIL = (WITH_SEARCH + [K["co-authored with"], K["co-authored by"], K["citing"]]
            + [K["in " + k] for k in C.IN_KEYS.values()]
            + [K["in the collection"], K["citing works in the collection"],
               K["with … as corresponding author"], K["under the … license"], K["before"],
               K["through"], K["where"]])
_BY_SPLIT = _e("by", "keyword", "split into rows: by year, by country",
               "`get the count of works about kelp by country`. A second split: `by year and "
               "country`.")


# the works-slot words the walker matches (slot words; the `in <key>` ones are `in`'s
# remainders, `with ... in <place>` is `with` and a search)
_WS_MATCH = _ptable(["about", "with", "citing", "co-authored by", "from", "by", "in", "where",
                     "under the"] + list(C.LINK_SLOTS))
_WS_SLOTS = {
    ("list", False): _Slot("works-slot", _WS_HEAD + _WS_TAIL + _after_comma(LIST_ORDERS), table=_WS_MATCH),
    ("list", True): _Slot("works-slot", _WS_HEAD + _WS_TAIL + _after_comma(LIST_ORDERS_SEARCH),
                          table=_WS_MATCH),
    ("table", False): _Slot("works-slot", [_BY_SPLIT if o is K["by"] else o for o in _WS_HEAD] + _WS_TAIL,
                            table=_WS_MATCH),
    ("only", False): _Slot("works-slot", _WS_HEAD + _WS_TAIL, table=_WS_MATCH),
}
_WS_SLOTS[("table", True)] = _WS_SLOTS[("table", False)]
_WS_SLOTS[("only", True)] = _WS_SLOTS[("only", False)]
S_ORDER_LIST = {False: _Slot("order", LIST_ORDERS), True: _Slot("order", LIST_ORDERS_SEARCH)}
S_ORDER_NUMBER = _Slot("order")


def _link_slot(entities, remainders=(), years=None, group=None):
    return _Slot("entity", list(remainders), entities=entities, years=years, group=group,
                 group_entities=entities if group == "values" else ())


S_FROM = _link_slot(_FROM_ENTITIES, [K["both"], K["all of"], K["the collection"]], years="from")
S_FROM_MANY = _link_slot(_FROM_ENTITIES)
S_IN = _link_slot(_ent("primary_location.source.id"),
                  [K[k] for k in C.IN_KEYS.values()] + [K["the collection"]])
S_IN_KEY = {k: _link_slot(_ent(c)) for c, k in C.IN_KEYS.items()}
S_COLLECTION = _link_slot(["collections"])
S_CITING = _link_slot(_ent("referenced_works"), [K["works in the collection"]])
S_BY_AUTHOR = _link_slot(_ent("authorships.author.id"))
S_LICENSE = _link_slot(_ent("primary_location.license"))
S_LINK_SLOTS = {w: _link_slot(_ent(c)) for w, c in C.LINK_SLOTS.items()}
S_SPLIT_VALUES = {w: _Slot("entity", [_PAREN, K["the collection"]], group="values",
                           group_entities=_ent(c))
                  for w, c in C.DIM_COLUMNS.items() if w != "year"}


def _base(noun: Optional[str]) -> Optional[str]:
    """A things noun's base (`journals` -> `sources`)."""
    return C.NOUN_THING_TYPES.get(noun, (noun, None))[0]


def _split_column(word: str) -> Optional[str]:
    """The works column a split word groups by (`journal` -> the source column)."""
    if word in C.DIM_COLUMNS:
        return C.DIM_COLUMNS[word]
    return C.NOUN_THINGS.get(_base(C.SINGULAR_THING.get(word)))


@functools.lru_cache(maxsize=None)
def _key_orders(word: str) -> Tuple[Dict[str, Any], ...]:
    """`alphabetical by country` / `in institution ID order`, as the renderer writes them."""
    col = _split_column(word)
    return tuple(_order(C._key_order(col, word, d)[2:]) for d in (False, True)) if col else ()


def _thing_entities(base: str) -> List[str]:
    return _ent(C.NOUN_THINGS[base])


def _place_entities(base: str) -> List[str]:
    """Where things are (`in [Sweden](SE)`): an author's record is in a country; others
    sit in a country or a continent (oql_core._parse_things)."""
    return ["countries"] if base == "authors" else ["countries", "continents"]


# ---------------------------------------------------------------------------
# Tokens
# ---------------------------------------------------------------------------
class _Tok:
    __slots__ = ("kind", "text", "start", "end", "low", "id", "name", "link_end")

    def __init__(self, kind, text, start, end, id_=None, name=None, link_end=None):
        self.kind = kind          # W word, L link, PL link being typed, S/OS string (open),
        self.text = text          # G/OG group (open), C comma, P period
        self.start = start
        self.end = end
        self.low = text.lower()
        self.id = id_
        self.name = name
        self.link_end = link_end if link_end is not None else end

    @property
    def poss(self) -> bool:
        return self.kind == "L" and self.end > self.link_end

    def __repr__(self):  # pragma: no cover (debugging)
        return f"{self.kind}:{self.text!r}@{self.start}"


_PARTIAL_ID = re.compile(r"\]\([^()\s]*\)?")


def _tokens(q: str) -> List[_Tok]:
    out: List[_Tok] = []
    i, n = 0, len(q)
    while i < n:
        ch = q[i]
        if ch.isspace():
            i += 1
            continue
        if ch in "[(" and (m := (C._LINK if ch == "[" else C._BARE_LINK).match(q, i)):
            end = m.end()
            full = end + 2 if q.startswith("'s", end) and (end + 2 >= n or not q[end + 2].isalnum()) else end
            out.append(_Tok("L", q[i:full], i, full, m.group(2) if ch == "[" else m.group(1),
                            m.group(1) if ch == "[" else "", end))
            i = full
            continue
        if ch == "[":
            j = i + 1
            while j < n and q[j] not in "[]":
                j += 1
            if j < n and q[j] == "]":
                m = _PARTIAL_ID.match(q, j)
                j = m.end() if m else j + 1
            out.append(_Tok("PL", q[i:j], i, j))
            i = j
            continue
        if ch == "(":
            depth, j, quote = 0, i, False
            while j < n:
                c = q[j]
                if quote:
                    quote = c != '"'
                elif c == '"':
                    quote = True
                elif c == "(":
                    depth += 1
                elif c == ")":
                    depth -= 1
                    if depth == 0:
                        break
                j += 1
            if j < n:
                out.append(_Tok("G", q[i:j + 1], i, j + 1))
                i = j + 1
            else:
                out.append(_Tok("OG", q[i:], i, n))
                i = n
            continue
        if ch == '"':
            j = q.find('"', i + 1)
            if j < 0:
                out.append(_Tok("OS", q[i:], i, n))
                i = n
            else:
                out.append(_Tok("S", q[i:j + 1], i, j + 1))
                i = j + 1
            continue
        if ch == ",":
            out.append(_Tok("C", ",", i, i + 1))
            i += 1
            continue
        if ch == "." and (i + 1 >= n or q[i + 1].isspace()):
            out.append(_Tok("P", ".", i, i + 1))
            i += 1
            continue
        j = i
        while j < n and not q[j].isspace() and q[j] not in '[("':
            if q[j] == "," and not (j + 1 < n and q[j + 1].isdigit() and j > i and q[j - 1].isdigit()):
                break
            j += 1
        if j == i:      # a stray character
            j = i + 1
        text = q[i:j]
        if len(text) > 1 and text.endswith(".") and (j >= n or q[j].isspace()):
            out.append(_Tok("W", text[:-1], i, j - 1))
            out.append(_Tok("P", ".", j - 1, j))
        else:
            out.append(_Tok("W", text, i, j))
        i = j
    return out


# ---------------------------------------------------------------------------
# The walker
# ---------------------------------------------------------------------------
class _Stop(Exception):
    """The walk reached the cursor: `slot` fits here; `pending` is the index of the first
    word already typed of a phrase in this slot (the prefix starts there)."""

    def __init__(self, slot, pending=None, extra=()):
        super().__init__()
        self.slot = slot
        self.pending = pending
        self.extra = list(extra)


class _Delegate(Exception):
    """The cursor is in a `where` tail: today's resolver answers."""

    def __init__(self, entity, start, end):
        super().__init__()
        self.entity, self.start, self.end = entity, start, end


_SPLIT_TABLE = _ptable(SPLITS)
_MEASURE_TABLE = _ptable(MAIN_MEASURES)
_SHOW_TABLE = _ptable(SHOW_MEASURES + _HOVER_ONLY)
_NOUN_TABLE = _ptable(list(ADJECTIVES) + list(NOUNS) + ["all"])
_HEAD_ONLY_TABLE = _ptable(["the"] + list(THINGS))
_THING_PLURAL_TABLE = _ptable(THINGS)
_SENTENCE_TABLE = _ptable(SENTENCE)
_COMPARATOR_TABLE = _ptable(COMPARATORS)
_COLLECTION_TABLE = _ptable([K["the collection"]])
_MEASURE_JOINS = {"of", *C.MEASURE_JOIN.values()}


class _Walk:
    def __init__(self, q: str, toks: List[_Tok], limit: int, cpos: Optional[int] = None):
        self.q = q
        self.t = toks
        self.n = limit
        self.i = 0
        self.cpos = cpos              # set: a cursor inside a `where` tail delegates
        self.choices: List[Tuple[_Slot, int, int, str]] = []
        self.kind = None              # list | things | number | table
        self.entity = None
        self.search = False
        self.splits: List[str] = []
        self.measures: List[str] = []
        self.thing_split: Optional[str] = None
        self.works_start = 0           # the token a works phrase starts at
        self.works_text: Optional[str] = None   # a table's works phrase, for its `Only`
        self.skipped = 0              # words the walk didn't know (tests: 0 on every core case)

    def skip(self):
        self.i += 1
        self.skipped += 1

    # -- cursor over the tokens before the limit
    def tok(self, k=0) -> Optional[_Tok]:
        j = self.i + k
        return self.t[j] if j < self.n else None

    def low(self, k=0) -> Optional[str]:
        t = self.tok(k)
        return t.low if t is not None and t.kind == "W" else None

    def match(self, table, slot, record=False) -> Optional[str]:
        """The longest phrase of `table` at the cursor: consume it and return its value.
        Words that run out mid-phrase stop the walk there (`funded b` -> prefix `funded b`)."""
        t0 = self.tok()
        if t0 is None or t0.kind in ("L", "PL", "C", "P"):
            return None
        partial = False
        for words, value in table.get(t0.low, ()):
            k, ok = 0, True
            for w in words:
                t = self.tok(k)
                if t is None:
                    break
                if t.kind in ("L", "PL", "C", "P") or t.low != w:
                    ok = False
                    break
                k += 1
            if ok and k == len(words):
                start = self.i
                self.i += k
                if record:
                    self.choices.append((slot() if callable(slot) else slot, start, self.i, value))
                return value
            if ok and k and self.i + k >= self.n:
                partial = True
        if partial:
            raise _Stop(slot() if callable(slot) else slot, self.i)
        return None

    def stop(self, slot, extra=()):
        raise _Stop(slot() if callable(slot) else slot, None, extra)

    def edge(self, t: Optional[_Tok], slot, comma: bool = True) -> bool:
        """What every phrase loop checks first: the cursor (stop with `slot`), the order's
        comma, a sentence's period, a link being typed, a token no phrase takes. True: the
        token was handled (the loop goes on). `order()` and `sentences()` end the walk."""
        if t is None:
            self.stop(slot)
        if t.kind == "C" and comma:
            self.i += 1
            self.order()
        if t.kind == "P":
            self.i += 1
            self.sentences()
        if t.kind == "PL":
            raise _Stop(slot() if callable(slot) else slot, self.i)
        if t.kind != "W":
            self.skip()
            return True
        return False

    # -- statements
    def run(self):
        if self.low() != "get":
            self.stop(S_START)
        self.i += 1
        t = self.tok()
        if t is None:
            self.stop(S_HEAD)
        if t.kind == "W":
            v = self.match(_HEAD_ONLY_TABLE, S_HEAD)
            if v == "the":
                self.kind, self.entity = "number", "works"
                return self.measure_list(main=True)
            if v is not None:
                self.choices.append((S_CHOICE_THING_NOUN, self.i - 1, self.i, v))
                base = _base(v)
                self.kind, self.entity = "things", base
                return self.things(base)
        self.kind, self.entity = "list", "works"
        self.works_phrase(S_HEAD, "list")

    def works_phrase(self, first: _Slot, ctx: str):
        self.works_start = self.i
        slot = first
        t = self.tok()
        if t is None:
            self.stop(slot)
        if t.kind == "L":
            self.i += 1
            if not t.poss and self.tok() is None:
                self.stop(S_POSS)
            slot = S_NOUN
        elif t.kind == "PL":
            raise _Stop(slot, self.i)
        while True:
            if self.tok() is None:
                self.stop(slot)
            start = self.i
            v = self.match(_NOUN_TABLE, slot)
            if v is None:
                self.skip()               # tolerate a word we don't know
                continue
            if v in ADJECTIVES:
                self.choices.append((S_CHOICE_ADJ, start, self.i, v))
                slot = S_NOUN
                continue
            if v == "all":
                continue
            self.choices.append((S_CHOICE_WORKS_NOUN, start, self.i, v))
            break
        self.works_slots(ctx)

    def ws_slot(self, ctx: str) -> _Slot:
        return _WS_SLOTS[(ctx, self.search)]

    def works_slots(self, ctx: str):
        """`about ...`, `since 2020`, `from [X]`, ... in any order (oql_core._parse_works)."""
        while True:
            if self.edge(self.tok(), lambda: self.ws_slot(ctx), comma=ctx != "only"):
                continue
            if self.years(strict=False):
                continue
            v = self.match(_WS_MATCH, lambda: self.ws_slot(ctx))
            if v is None:
                self.skip()
                continue
            self.slot_word(v, ctx)

    def slot_word(self, v: str, ctx: str):
        """One works-slot phrase (a table's `by <split>` ends the walk there)."""
        after = lambda: self.ws_slot(ctx)  # noqa: E731
        if v == "about":
            self.search = True
            self.search_term(S_ABOUT)
        elif v == "with":
            t = self.tok()
            if t is not None and t.kind == "L":
                self.i += 1
                self.expect(S_CORRESPONDING_WORD)
            else:
                self.search = True
                self.search_term(S_SEARCH)
                self.expect(S_PLACE)
        elif v == "citing":
            if self.links(S_CITING, after) == "works in the collection":
                self.links(S_COLLECTION, after)
        elif v == "co-authored by":
            self.links(S_BY_AUTHOR, after, sep=("and", ","))
        elif v == "from":
            x = self.links(S_FROM, after)
            if x in ("both", "all of"):
                self.links(S_FROM_MANY, after, sep=("and", ","))
            elif x == "the collection":
                self.links(S_COLLECTION, after)
        elif v == "by":
            if ctx == "table":
                t = self.tok()
                if t is None:
                    self.stop(S_SPLIT)
                if t.kind == "L":
                    self.links(S_BY_AUTHOR, after)
                    return
                if t.kind == "PL":
                    raise _Stop(S_SPLIT, self.i)
                self.works_text = " ".join(
                    self.q[self.t[self.works_start].start:self.t[self.i - 2].end].split())
                self.split_list()
            self.links(S_BY_AUTHOR, after)
        elif v == "in":
            x = self.links(S_IN, after)
            if x == "the collection":
                self.links(S_COLLECTION, after)
            elif isinstance(x, str) and x in S_IN_KEY:
                self.links(S_IN_KEY[x], after)
        elif v in C.LINK_SLOTS:
            self.links(S_LINK_SLOTS[v], after)
        elif v == "under the":
            self.link(S_LICENSE)
            self.expect(S_LICENSE_WORD)
        elif v == "where":
            self.where_tail("works", ctx)

    def expect(self, slot: _Slot):
        if self.tok() is None:
            self.stop(slot)
        self.match(slot.table, slot)

    def search_term(self, slot: _Slot):
        t = self.tok()
        if t is None:
            self.stop(slot)
        if t.kind == "PL" and slot.bracket_entities:
            raise _Stop(slot, self.i)
        self.i += 1

    def link(self, slot: _Slot):
        """One link, or a word that names what comes next (`both`, `the topic`, a year)."""
        t = self.tok()
        if t is None:
            self.stop(slot)
        if t.kind == "L":
            self.i += 1
            return t
        if t.kind == "PL":
            raise _Stop(slot, self.i)
        if t.kind == "G" and slot.group == "values":
            self.i += 1
            return t
        if t.kind != "W":
            self.skip()
            return None
        if slot.table:
            v = self.match(slot.table, slot)
            if v is not None:
                return v
        if slot.years and _YEARISH.fullmatch(t.low):
            self.choices.append((S_YEAR[slot.years], self.i, self.i + 1, t.text))
            self.i += 1
            return "year"
        raise _Stop(slot, self.i)          # a name being typed without its `[`

    def links(self, slot: _Slot, after, sep=("or",)):
        """A link and more joined by `or` (or `and`, `,`), as `_links_list` reads them."""
        x = self.link(slot)
        joiners = [K[s] for s in sep if s in K]
        while isinstance(x, _Tok):
            t = self.tok()
            if t is None:
                self.stop(after, extra=joiners)
            if (t.kind == "W" and t.low in sep) or (t.kind == "C" and "," in sep):
                self.i += 1
                if t.kind == "C" and self.low() == "and":
                    self.i += 1
                x = self.link(slot)
                continue
            break
        return x

    def years(self, strict: bool) -> bool:
        """`since 2020`, `from 2018–2025`, `from 2020 through 2024`, `published since 2020`
        (oql_core._years_from). `strict`: the year word can only mean a year here."""
        j = 1 if self.low() == "published" and self.low(1) in C.YEAR_OPS else 0
        w = self.low(j)
        if w not in C.YEAR_OPS:
            return False
        nxt = self.tok(j + 1)
        if nxt is None:
            if strict or w in ("since", "before", "through"):
                self.i += j + 1
                self.stop(S_YEAR[w])
            return False
        if nxt.kind != "W" or not _YEARISH.fullmatch(nxt.low):
            if strict or w in ("since", "before", "through"):
                self.i += j + 1
                return True
            return False
        self.i += j + 1
        self.choices.append((S_YEAR[w], self.i, self.i + 1, nxt.text))
        self.i += 1
        if w == "from" and self.low() == "through":
            nxt2 = self.tok(1)
            if nxt2 is None:
                self.i += 1
                self.stop(S_YEAR["through"])
            if nxt2.kind == "W" and _YEARISH.fullmatch(nxt2.low):
                self.choices.append((S_YEAR["through"], self.i + 1, self.i + 2, nxt2.text))
                self.i += 2
        return True

    def where_tail(self, entity: str, ctx: str):
        """`where <key-value conditions>`: today's grammar. The tail runs to the order's
        comma, a sentence's period, or a table's `by <split>` (`and <split>` after a split)."""
        wtok = self.t[self.i - 1]
        j = self.i
        while j < len(self.t):
            t = self.t[j]
            if t.kind in ("C", "P"):
                break
            if t.kind == "W" and ((ctx == "table" and t.low == "by")    # today's grammar has no `by`
                                  or (ctx == "split" and t.low == "and" and self.split_at(j + 1))):
                break
            j += 1
        end = self.t[j].start if j < len(self.t) else len(self.q)
        if self.cpos is not None and wtok.end < self.cpos <= end:
            raise _Delegate(entity, wtok.end, end)
        self.i = min(j, self.n)

    def split_at(self, j: int) -> bool:
        if j >= len(self.t) or self.t[j].kind != "W":
            return False
        for words, _ in _SPLIT_TABLE.get(self.t[j].low, ()):
            if all(j + k < len(self.t) and self.t[j + k].kind == "W" and self.t[j + k].low == w
                   for k, w in enumerate(words)):
                return True
        return False

    # -- numbers and tables
    def measure_list(self, main: bool):
        """`count, sum of citations, and mean FWCI` then `of` (or `to`, `for`)."""
        slot = S_MEASURE if main else S_MEASURE_SHOW
        table = _MEASURE_TABLE if main else _SHOW_TABLE
        while True:
            if self.tok() is None:
                self.stop(slot)
            v = self.match(table, slot, record=True)
            if v is None:
                t = self.tok()
                self.skip()
                if t.kind == "P" and not main:
                    return
                continue
            self.measures.append(C.TABLE_NAMES.get(v, v))
            while True:
                t = self.tok()
                if t is None:
                    self.stop(self.measure_next(main, v))
                if t.kind == "C":
                    self.i += 1
                    if self.low() == "and":
                        self.i += 1
                    break
                if t.kind == "P" and not main:
                    self.i += 1
                    return
                if t.low == "and":
                    self.i += 1
                    break
                if main and t.kind == "W" and t.low in _MEASURE_JOINS:
                    self.i += 1
                    return self.works_phrase(S_NOUN_TABLE, "table")
                self.skip()

    def measure_next(self, main: bool, last: str) -> _Slot:
        if not main:
            return _Slot("measure", [K["and"]])
        join = C.MEASURE_JOIN.get(last)
        opts = [K["and"]] + ([K[join]] if join else []) + [K["of"]]
        return _Slot("measure", opts)

    def split_list(self):
        """`by year since 2004 and country in (...)` (oql_core._parse_table)."""
        while True:
            if self.tok() is None:
                self.stop(S_SPLIT)
            v = self.match(_SPLIT_TABLE, S_SPLIT, record=True)
            if v is None:
                t = self.tok()
                if t.kind == "PL":
                    raise _Stop(S_SPLIT, self.i)
                self.skip()
                continue
            self.kind = "table"
            self.splits.append(v)
            if v in C.SINGULAR_THING:
                self.thing_split = self.thing_split or C.SINGULAR_THING[v]
            self.after_split(v)          # returns only after `and`: the next split

    def after_split_slot(self, word: str) -> _Slot:
        opts = []
        if len(self.splits) == 1:
            opts.append(_with(K["and"], detail="a second split: by year and country"))
        if word == "year":
            opts += [K["since"], K["from"], K["before"], K["through"]]
        else:
            if word in C.DIM_COLUMNS:
                opts += [_VALUES_IN, K["in the collection"]]
            if word in C.SINGULAR_THING:
                opts += _thing_words(_base(C.SINGULAR_THING[word]))
        opts += _after_comma(self.table_orders())
        opts += self.sentence_options(insert=". ")
        return _Slot("split", opts, table=_THING_TABLE)

    def after_split(self, word: str):
        thing = word in C.SINGULAR_THING
        base = _base(C.SINGULAR_THING.get(word))
        slot = lambda: self.after_split_slot(word)  # noqa: E731
        while True:
            t = self.tok()
            if self.edge(t, slot):
                continue
            if t.low == "and" and len(self.splits) == 1:
                self.i += 1
                return
            if word == "year":
                if self.years(strict=True):
                    continue
                self.skip()
                continue
            v = self.match(_THING_TABLE, slot)
            if v is None:
                self.skip()
                continue
            if v == "in":
                in_slot = lambda: self.split_in_slot(word, base)  # noqa: E731
                nt = self.tok()
                if nt is None:
                    self.stop(in_slot)
                if nt.kind in ("G", "OG"):
                    self.i += 1
                    continue
                if nt.kind == "W" and self.match(_COLLECTION_TABLE, in_slot):
                    self.link(S_COLLECTION)
                    continue
                self.link(in_slot())
            elif v == "in the collection":
                self.link(S_COLLECTION)
            elif thing:
                self.thing_word(v, base, "split", slot)

    def split_in_slot(self, word: str, base: Optional[str]) -> _Slot:
        """After `by <split> in`: a list of values `(...)` (a dimension) or the things'
        own place `[Sweden](SE)` (a thing)."""
        opts, ents = [], []
        if word in C.DIM_COLUMNS and word != "year":
            opts += [_PAREN, K["the collection"]]
        if base is not None:
            ents = _place_entities(base)
        vals = S_SPLIT_VALUES.get(word)
        return _Slot("entity", opts, entities=ents, group="values",
                     group_entities=vals.group_entities if vals else ents)

    def table_orders(self) -> List[Dict[str, Any]]:
        """The orders a table reads (oql_core._TABLE_ORDER_RE / _table_order)."""
        out = []
        first = self.splits[0] if self.splits else None
        if first == "year":
            out += [_order("oldest first"), _order("newest first")]
        out += [_order("most works first"), _order("fewest works first")]   # the default too
        nums = [m for m in self.measures if m not in _OWN_NAMES]
        if len(nums) == 1 and nums[0] != "count":
            out += [_order("highest first"), _order("lowest first")]
        elif len(nums) > 1:
            for m in nums:
                if m != "count":
                    out += [_order(f"highest {m} first"), _order(f"lowest {m} first")]
        if first is not None and first != "year":
            out += _key_orders(first)
        if self.thing_split:
            for w in _OWN_NAMES:
                out += [_order(f"highest {w} first"), _order(f"lowest {w} first")]
        return out

    def sentence_options(self, insert: str = "") -> List[Dict[str, Any]]:
        if self.kind not in ("table", "things"):
            return []
        out = [SENTENCE["Show"]]
        if self.kind == "table" and self.thing_split:
            out.append(SENTENCE["Only"])
        return [_with(o, insert=insert + o["value"] + " ") for o in out] if insert else out

    # -- things
    def things(self, base: str):
        """A list of things by their own fields (oql_core._parse_things_list)."""
        slot = lambda: _things_slot(base)  # noqa: E731
        while True:
            if self.edge(self.tok(), slot):
                continue
            v = self.match(_THING_TABLE, slot)
            if v is None:
                self.skip()
                continue
            self.thing_word(v, base, "list", slot)

    def thing_word(self, v: str, base: str, ctx: str, after):
        if v in ("at", "ever at"):
            self.link(_link_slot(["institutions"]))
            self.record_years(after)
        elif v in ("in", "ever in"):
            rem = [K[k] for k in C.THING_IN_KEYS.values()] if base in _IN_KEY_THINGS and ctx == "list" else []
            x = self.link(_link_slot(_place_entities(base), rem))
            if isinstance(x, str) and x in C.KEY_THING_IN:
                self.link(_link_slot(_ent(C.KEY_THING_IN[x])))
            elif base == "authors" and isinstance(x, _Tok):
                self.record_years(after)
        elif v in ("except", "other than"):
            self.link(_link_slot(_thing_entities(base), group="values"))
        elif v in _THRESHOLD_VALUES:
            t = self.tok()
            if t is None:
                self.stop(S_NUMBER)
            self.i += 1
        elif v == "where":
            self.where_tail(base, ctx)

    def record_years(self, after):
        """An author's record years: `since 2022`, `in 2+ years`, in either order."""
        while True:
            t = self.tok()
            if t is None:
                self.stop(after, extra=_RECORD_YEARS)
            if t.kind == "W" and t.low == "in" and re.fullmatch(r"\d\+", self.low(1) or "") \
                    and self.low(2) == "years":
                self.i += 3
                continue
            if t.kind == "W" and t.low in C.YEAR_OPS and t.low != "in":
                if self.years(strict=True):
                    continue
            return

    # -- the end of the main sentence
    def order_slot(self) -> _Slot:
        if self.kind == "table":
            return _Slot("order", self.table_orders())
        if self.kind == "things":
            return _things_order_slot(self.entity)
        if self.kind == "number":
            return S_ORDER_NUMBER
        return S_ORDER_LIST[self.search]

    def order(self):
        slot = self.order_slot()
        if self.tok() is None:
            self.stop(slot)
        v = self.match(slot.table, slot, record=True)
        if v is None:            # any order the parser reads (`highest mean FWCI first` adds it)
            v = self.match(_ORDER_ALL, slot, record=True)
        if v is None:
            self.skip()
        while True:
            t = self.tok()
            if t is None:
                self.stop(_Slot("end", self.sentence_options(insert=". ")))
            if t.kind == "P":
                self.i += 1
                return self.sentences()
            self.skip()

    def sentences(self):
        """`Show h-index.` and `Only institutions with at least 10 works about kelp.`"""
        while True:
            t = self.tok()
            if t is None:
                before = self.q[self.t[self.i - 1].end:self.t[self.i - 1].end + 1] if self.i else ""
                opts = [_with(o, insert=("" if before.isspace() else " ") + o["value"] + " ")
                        for o in self.sentence_options()]
                self.stop(_Slot("sentence", opts))
            v = self.match(_SENTENCE_TABLE, lambda: _Slot("sentence", self.sentence_options()))
            if v == "Show":
                self.measure_list(main=False)
            elif v == "Only":
                self.only()
            else:
                self.skip()

    def only(self):
        nouns = [THINGS[self.thing_split]] if self.thing_split in THINGS else list(THINGS.values())
        slot = _Slot("noun", nouns, table=_THING_PLURAL_TABLE)
        if self.tok() is None:
            self.stop(slot)
        if self.match(_THING_PLURAL_TABLE, slot) is None:
            self.skip()
        if self.tok() is None:
            self.stop(S_COMPARATOR)
        if self.match(_COMPARATOR_TABLE, S_COMPARATOR) is None:
            return
        if self.tok() is None:
            self.stop(S_NUMBER)
        self.i += 1
        works = self.works_text
        first = _Slot("noun", ([_e(works, "sentence", "the same works as the table",
                                   "A count floor counts the table's own works: `Only institutions "
                                   "with at least 10 works about kelp.`")] if works else [])
                      + _WORK_NOUNS)
        self.works_phrase(first, "only")


# what may follow a thing (a list's noun or a split word): `at [X]`, `in [X]`, `except [X]`,
# `with an h-index above N`, `where ...` (oql_core._parse_things), and a dimension's
# `in (...)` / `in the collection [X]` (oql_core._parse_dim)
_THING_TABLE = _ptable(["in", "in the collection", "at", "ever at", "ever in", "except", "other than",
                        "where"] + [x["value"] for x in THRESHOLDS])
_THRESHOLD_VALUES = {x["value"] for x in THRESHOLDS}
_IN_KEY_THINGS = {_base(n) for n in ("topics", "subfields", "fields")}
S_COMPARATOR = _Slot("things-slot", COMPARATORS)


def _thing_words(base: str) -> List[Dict[str, Any]]:
    """The words offered after a thing: its record or place, leaving some out, its own
    numbers, `where`."""
    return ([K["at"]] if base == "authors" else []) + [_THING_IN, K["except"]] + _SHOWN_THRESHOLDS \
        + [K["where"]]


@functools.lru_cache(maxsize=None)
def _things_slot(base: str) -> _Slot:
    opts = _thing_words(base)
    if base in _IN_KEY_THINGS:
        opts += [K["in " + k] for k in C.THING_IN_KEYS.values()]
    return _Slot("things-slot", opts + _after_comma(_things_orders(base)), table=_THING_TABLE)


@functools.lru_cache(maxsize=None)
def _things_order_slot(base: str) -> _Slot:
    return _Slot("order", _things_orders(base))


# ---------------------------------------------------------------------------
# Replies
# ---------------------------------------------------------------------------
def _tidy(prefix: str) -> str:
    """The prefix with its spaces collapsed, keeping one trailing space (`funded `)."""
    p = " ".join(prefix.split())
    return p + " " if p and prefix[-1:].isspace() else p


def _filter(options: List[Dict[str, Any]], prefix: str) -> List[Dict[str, Any]]:
    p = _tidy(prefix).lower()
    seen, first, later = set(), [], []
    for o in options:
        v = o["value"]
        if v in seen:
            continue
        lv = v.lower()
        if not p or lv.startswith(p):
            first.append(o)
            seen.add(v)
        elif " " not in p.strip() and any(w.startswith(p) for w in lv.split()[1:]):
            later.append(o)
            seen.add(v)
    return [dict(o) for o in first + later]


def _ctx(slot_name, prefix, start, end, suggestions, entities) -> Dict[str, Any]:
    return {"category": "core", "slot": slot_name, "prefix": prefix,
            "replace_range": {"start": start, "end": end}, "suggestions": suggestions,
            "autocomplete_entities": list(entities)}


def _reply(entity, ctx) -> Dict[str, Any]:
    return {"entity": entity, "context": ctx, "diagnostic": None}


def none_reply(cpos: int, entity=None) -> Dict[str, Any]:
    return _reply(entity, {"category": "none", "slot": "none", "prefix": "",
                           "replace_range": {"start": cpos, "end": cpos}, "suggestions": [],
                           "autocomplete_entities": []})


def _options(slot: _Slot, extra=()) -> List[Dict[str, Any]]:
    opts = list(extra) + slot.options
    if slot.years:
        opts = opts + _year_entries(slot.years)
    return opts


def _walk(q, toks, limit, cpos=None) -> Tuple[_Walk, Optional[Exception]]:
    w = _Walk(q, toks, limit, cpos)
    try:
        w.run()
    except (_Stop, _Delegate) as e:
        return w, e
    return w, None


def _cursor_token(toks: List[_Tok], cpos: int):
    for idx, t in enumerate(toks):
        if t.start >= cpos:
            break
        if t.kind in ("W", "PL") and cpos <= t.end:
            return idx, t
        if t.kind == "L" and cpos < t.link_end:
            return idx, t
        if t.kind in ("S", "G") and cpos < t.end:
            return idx, t
        if t.kind in ("OS", "OG"):
            return idx, t
    return None, None


def _word_end(q: str, cpos: int, limit: int) -> int:
    j = cpos
    while j < limit and not q[j].isspace() and q[j] not in "[](),":
        j += 1
    return j


def core_context(q: str, pos: Optional[int] = None) -> Dict[str, Any]:
    """The editor context for a core v3 statement at code-point offset `pos`."""
    cpos = clamp(q, pos)
    toks = _tokens(q)
    idx, cur = _cursor_token(toks, cpos)

    # 1. a click inside a written phrase of a choice slot: its alternatives, as a dropdown
    # (at the very end the cursor is typing, never clicking)
    if (cur is None or cur.kind == "W") and toks and cpos < toks[-1].end:
        w, _ = _walk(q, toks, len(toks))
        for slot, s, e, value in w.choices:
            a, b = toks[s].start, toks[e - 1].end
            if a <= cpos <= b and (cpos < b or e < len(toks)):
                return _reply(w.entity, _dropdown(slot, value, q[a:b], a, b))

    # 2. the words before the cursor: which slot, and what is typed of it
    limit = idx if idx is not None else sum(1 for t in toks if t.end <= cpos)
    w, stop = _walk(q, toks, limit, cpos)
    if isinstance(stop, _Delegate):
        return _delegate(q, cpos, stop)
    if not isinstance(stop, _Stop):
        return none_reply(cpos, w.entity)
    slot = stop.slot
    if cur is not None and cur.kind == "L":            # on a written link: swap it
        kind = C._kind_of(cur.id)
        ents = slot.group_entities or slot.entities or _STAR_ENTITIES
        ents = [kind] if kind in ents or (kind and not slot.entities) else ents
        return _reply(w.entity, _ctx("link", cur.name, cur.start, cur.link_end, [], ents))
    if cur is not None and cur.kind in ("G", "OG", "S", "OS"):
        if slot.group == "values" and cur.kind in ("G", "OG"):
            return _reply(w.entity, _values(q, cur, cpos, slot))
        if slot.group == "search":
            return _reply(w.entity, _ctx("search-text", "", cpos, cpos, [], []))
        return none_reply(cpos, w.entity)
    if stop.pending is not None:
        start = toks[stop.pending].start
    else:
        start = cur.start if cur is not None else cpos
    end = cur.end if cur is not None and cur.kind == "W" else \
        _word_end(q, cpos, cur.end) if cur is not None else cpos
    prefix = q[start:cpos]
    ents = slot.entities + ([e for e in slot.bracket_entities if e not in slot.entities]
                            if prefix.startswith("[") else [])
    return _reply(w.entity, _ctx(slot.name, _tidy(prefix), start, end,
                                 _filter(_options(slot, stop.extra), prefix), ents))


def _dropdown(slot: _Slot, value: str, written: str, a: int, b: int) -> Dict[str, Any]:
    opts = _options(slot)
    cur = next((o for o in opts if o["value"].lower() == value.lower()), None)
    if cur is None:
        cur = _year(slot.years, written) if slot.years else \
            _e(written, opts[0]["kind"] if opts else "keyword", "as written", f"`{written}`")
    rest = [dict(o) for o in opts if o["value"].lower() != value.lower()]
    return _ctx(slot.name, "", a, b, [_with(cur, current=True)] + rest, [])


def _values(q: str, group: _Tok, cpos: int, slot: _Slot) -> Dict[str, Any]:
    """Inside `( ... )`: a list of links. The item at the cursor is the prefix."""
    sub = _tokens(q[group.start + 1:group.end - (1 if group.kind == "G" else 0)])
    off = group.start + 1
    ents = slot.group_entities or slot.entities
    start = off
    for t in sub:
        a, b = t.start + off, t.end + off
        if a >= cpos:
            break
        if t.kind == "L" and a < cpos < t.link_end + off:
            return _ctx("link", t.name, a, t.link_end + off, [], [C._kind_of(t.id) or ents[0]]
                        if ents else [])
        if t.kind == "C" or (t.kind == "W" and t.low in ("or", "and")) or t.kind == "L":
            start = b
    while start < cpos and q[start].isspace():
        start += 1
    end = _word_end(q, cpos, group.end - (1 if group.kind == "G" else 0))
    prefix = q[start:cpos]
    return _ctx("entity", " ".join(prefix.split()), start, max(end, cpos), [], ents)


def _delegate(q: str, cpos: int, d: _Delegate) -> Dict[str, Any]:
    """Today's resolver on `get <entity> where <tail>`, offsets shifted back to `q`."""
    from query_translation.oql_context import _parse_context_old
    head = f"get {d.entity} where"
    eq = head + q[d.start:d.end]
    shift = d.start - len(head)
    r = _parse_context_old(eq, cpos - shift)
    ctx = r.get("context") or {}
    for holder, key in ((ctx, "replace_range"), (ctx.get("sibling") or {}, "clause_range"),
                        (ctx.get("sibling") or {}, "value_range")):
        if holder.get(key):
            holder[key] = {"start": holder[key]["start"] + shift, "end": holder[key]["end"] + shift}
    if ctx.get("suggestions"):
        # `group by`, `sample`, `where` are today's directives; a core statement goes on
        # with its own words (`, <order>`, `by <split>`), not those
        ctx["suggestions"] = [s for s in ctx["suggestions"] if s.get("kind") != "directive"]
    diag = r.get("diagnostic")
    if diag and diag.get("position") is not None:
        diag["position"] += shift
    return r


# ---------------------------------------------------------------------------
# GET /oql-vocabulary: every phrase the core grammar has, for hover help
# ---------------------------------------------------------------------------
def _vocabulary() -> List[Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}

    def add(entries):
        for o in entries:
            if o["value"] not in out:
                out[o["value"]] = {k: o[k] for k in ("value", "kind", "detail", "doc")}

    add(K.values())
    add([_BY_SPLIT, _THING_IN, _VALUES_IN])
    add(NOUNS.values())
    add(ADJECTIVES.values())
    add(THINGS.values())
    add(MEASURES.values())
    add(_HOVER_ONLY)
    add(SPLITS.values())
    add(SENTENCE.values())
    add(LIST_ORDERS_SEARCH + [_order("best matches first")])
    for base in C.NOUN_THINGS:
        add(_things_orders(base))
    add([_order(p) for p in ("most works first", "fewest works first", "highest first", "lowest first")])
    for m in MAIN_MEASURES:
        if m["value"] != "count":
            add([_order(f"highest {m['value']} first"), _order(f"lowest {m['value']} first")])
    for word in C._SPLIT_WORDS:
        if word != "year":
            add(_key_orders(word))
    return list(out.values())


VOCABULARY = _vocabulary()
_ORDER_ALL = _ptable([o for o in VOCABULARY if o["kind"] == "order"])
_RECORD_YEARS = [_with(K[w], detail=d) for w, d in (("since", "on their record since a year"),
                                                     ("through", "on their record through a year"))] \
    + [K["in 2+ years"]]
