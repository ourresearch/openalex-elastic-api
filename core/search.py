import re

from elasticsearch_dsl import Q

from core.exceptions import APIQueryParamsError
from core.knn import KNNQuery
import requests

from settings import ES_URL_WALDEN


MAX_LONG_PHRASES_IN_OR = 3
LONG_PHRASE_CHAR_THRESHOLD = 80
QUOTED_PHRASE_RE = re.compile(r'"([^"]*)"')
# A single quoted phrase carrying a proximity slop, e.g. `"smart phone"~3`. When the
# phrase ALSO contains a wildcard (`"smart phone*"~3`), the engine builds an ES
# `intervals` query instead of query_string (which silently drops the wildcard) — see
# proximity_wildcard_query() / oxjob #355.
PROXIMITY_PHRASE_RE = re.compile(r'^"([^"]*)"~(\d+)$')
# A single quoted phrase with NO proximity slop, e.g. `"smart* phone"`. When it is
# multi-token AND contains a wildcard, the engine builds an ES `intervals` ADJACENCY
# query (ordered=true, max_gaps=0) — query_string would silently drop the wildcard, so
# this is the no-`~N` sibling of the proximity case — see adjacent_wildcard_query() /
# oxjob #355 (Goal A).
ADJACENT_PHRASE_RE = re.compile(r'^"([^"]*)"$')
# Binary proximity: two SEPARATE quoted operands joined by a slop, e.g.
# `"smart"~3~"phone"` (OQL `"smart" within 3 words of "phone"`). Either operand may
# itself be a multi-word phrase (`"machine learning"~5~"neural network"`). This is the
# WoS `NEAR/N` shape that `match_phrase`+slop genuinely cannot express (slop is
# whole-phrase): each operand is its own ordered sub-interval and the two are combined
# unordered with max_gaps=N. Built as an ES `intervals` query — see
# binary_proximity_query() / oxjob #355 (Goal B).
BINARY_PROXIMITY_RE = re.compile(r'^"([^"]*)"~(\d+)~"([^"]*)"$')

# oxjob #355 perf guard: two short prefix-wildcards in one `intervals` query multiply
# postings expansion (live on works-v33: `"pro* pro*"` ~265ms vs ~45ms once each prefix
# is >=4 chars). Cap wildcard tokens per intervals query and require longer prefixes
# when there are two. A lone wildcard keeps #337's >=3-char floor.
MAX_WILDCARDS_PER_INTERVALS = 2
MULTI_WILDCARD_MIN_PREFIX = 4

# #364: stemmed text fields whose wildcards are silently wrong. Stemming happens
# at INDEX time, so the literal prefix the user types (e.g. `studies` in
# `studies*`) is usually absent from the stemmed index (it was stored as `studi`)
# and the wildcard matches ~nothing (live: `studies*` = 2,423 stemmed vs
# 2,210,904 no-stem, works-v33). A wildcard must target the no-stem `.exact`
# field instead. This maps each stemmed `.search` param → the `.search.exact`
# param a wildcard has to use. Works-only: the `.no_stem` ES subfields these
# point at exist on the works index. Other entities' `default.search`/
# `display_name.search` have no no-stem sibling and are left unchanged (a
# follow-up would need no-stem mappings added to those indices).
WILDCARD_REQUIRES_EXACT = {
    "default.search": "default.search.exact",
    "title.search": "title.search.exact",
    "abstract.search": "abstract.search.exact",
    "fulltext.search": "fulltext.search.exact",
    "display_name.search": "display_name.search.exact",
    "title_and_abstract.search": "title_and_abstract.search.exact",
}


def _has_unquoted_wildcard(search_terms):
    """True if a `*`/`?` wildcard appears OUTSIDE quotes (the stemmed-field path).

    A wildcard inside quotes is handled by validate_wildcards (rejected unless it
    carries a proximity slop `~N`, which the engine routes to a no-stem
    `intervals` query — oxjob #355). Only an UNQUOTED wildcard lands on the
    stemmed `.search` field, so that is the shape #364 gates.
    """
    if not search_terms or not isinstance(search_terms, str):
        return False
    unquoted = QUOTED_PHRASE_RE.sub(" ", search_terms)
    return any(("*" in word or "?" in word) for word in unquoted.split())


def validate_wildcard_requires_exact(param, search_terms, index):
    """#364: reject an (unquoted) wildcard on a stemmed `.search` field.

    Stemming removes the literal text the wildcard matches, so the search returns
    wrong/near-empty results. Point the user at the no-stem `.search.exact` field
    where the wildcard works. Mirrors the OQL diagnostic OQL_WILDCARD_NEEDS_EXACT
    so the raw API and OQL give identical guidance (the #337 invariant).
    """
    if not index or not index.lower().startswith("works"):
        return
    exact_param = WILDCARD_REQUIRES_EXACT.get(param)
    if not exact_param:
        return
    if _has_unquoted_wildcard(search_terms):
        raise APIQueryParamsError(
            f'Wildcards (* or ?) require the exact (no-stem) field. "{param}" is '
            "stemmed, so the literal text before the wildcard is removed when the "
            "work is indexed and the search returns wrong results. Use "
            f'"{exact_param}" instead, e.g. {exact_param}:{search_terms}.'
        )


def validate_top_level_search_wildcard(search_terms, index, is_exact):
    """#364: gate a wildcard on the top-level `?search=` / scoped-search path.

    The default top-level search is stemmed, so an (unquoted) wildcard there is
    silently wrong (same root cause as the filter form). Require the exact route
    (the `search.exact=` param, or the `default.search.exact` filter). `is_exact`
    is True when the caller already routes to the no-stem path (the `search.exact`
    / `search.title.exact` / `search.title_and_abstract.exact` params, which set
    search_type=exact), in which case the wildcard is fine. Works-only — other
    indices have no no-stem search path.
    """
    if is_exact or not index or not index.lower().startswith("works"):
        return
    if _has_unquoted_wildcard(search_terms):
        raise APIQueryParamsError(
            "Wildcards (* or ?) require exact (no-stem) search. The default search "
            "is stemmed, so the literal text before the wildcard is removed when "
            "the work is indexed and the search returns wrong results. Use the "
            "search.exact= parameter instead (or the default.search.exact filter), "
            f"e.g. search.exact={search_terms}."
        )


def _validate_wildcard_token(word):
    """Reject the wildcard shapes #337 closed; no-op for tokens without a wildcard.

    - leading `*`/`?` (e.g. `*phone`) reaches ES as a raw parse error
      ("Failed to parse query") because we pin allow_leading_wildcard=False;
    - a `*` with fewer than 3 leading characters (e.g. `ab*`) misses the wildcard
      detector and silently degrades to a literal that matches ~nothing.
    """
    if "*" not in word and "?" not in word:
        return
    # Leading wildcard attached to text (`*phone`, `?cycle`) — bare `*`/`?`
    # (length 1) is left alone; it isn't treated as a wildcard today.
    if len(word) > 1 and word[0] in "*?":
        raise APIQueryParamsError(
            f'Leading wildcards are not supported (too expensive): "{word}". '
            "Anchor the wildcard with at least 3 leading characters, e.g. cycle*."
        )
    # A `*` needs >=3 word characters before it (matches the engine detector).
    # star == 0 is a leading/bare `*` (handled above or left alone), not a prefix.
    star = word.find("*")
    if star > 0:
        chars_before = len(re.match(r"\w*", word).group(0)[:star])
        if chars_before < 3:
            raise APIQueryParamsError(
                f'A * wildcard needs at least 3 leading characters: "{word}". '
                "Add characters before the *, e.g. abc*."
            )


def _validate_wildcard_budget(words):
    """Cap prefix-expansion cost inside one ES `intervals` query (oxjob #355 guard).

    Two short prefix-wildcards in a single intervals query multiply postings-list
    expansion — live on works-v33 `"pro* pro*"` ran ~265ms vs ~45ms once each prefix
    is >=4 chars. So: at most MAX_WILDCARDS_PER_INTERVALS (2) wildcard tokens per
    query, and when there are exactly two, each TRAILING-`*` prefix token (the cost
    driver; `?`/embedded wildcards are bounded) needs >=MULTI_WILDCARD_MIN_PREFIX (4)
    leading chars. A lone wildcard is untouched (keeps #337's >=3-char floor), so the
    already-shipped single-wildcard adjacency/proximity cases (Goal A, L02c) don't
    regress. `words` is every token across the intervals query (both operands, for the
    binary case).
    """
    wild = [w for w in words if "*" in w or "?" in w]
    if len(wild) <= 1:
        return
    if len(wild) > MAX_WILDCARDS_PER_INTERVALS:
        raise APIQueryParamsError(
            f"At most {MAX_WILDCARDS_PER_INTERVALS} wildcards (* or ?) are allowed in "
            f"one phrase or proximity search; this has {len(wild)}. Remove a wildcard "
            "or split it into separate searches (it gets too expensive otherwise)."
        )
    for w in wild:
        # Only a trailing-`*` prefix drives the multiplicative expansion; require a
        # longer anchor for it when a second wildcard is present.
        if w.endswith("*") and w.count("*") == 1 and "?" not in w:
            if len(w) - 1 < MULTI_WILDCARD_MIN_PREFIX:
                raise APIQueryParamsError(
                    f"With two wildcards in one phrase or proximity search, each * "
                    f"needs at least {MULTI_WILDCARD_MIN_PREFIX} leading characters "
                    f'(for performance): "{w}". Use a longer prefix (e.g. abcd*), drop '
                    "a wildcard, or split into separate searches."
                )


def validate_wildcards(search_terms):
    """Reject unsupported wildcard shapes with friendly messages (oxjob #337).

    Mirrors the OQL v2 diagnostics (OQL_LEADING_WILDCARD, OQL_SHORT_WILDCARD_PREFIX,
    OQL_WILDCARD_IN_QUOTES) so the raw API and OQL give identical guidance. The
    "wildcards must target the no-stem field" rule (#364) is enforced separately by
    validate_wildcard_requires_exact (it needs the field param, not just the terms).

    One shape that LOOKS like wildcard-in-quotes is allowed: a wildcard inside a quoted
    PROXIMITY phrase, `"smart phone*"~3`. That compiles to an ES `intervals` query
    (oxjob #355) rather than being dropped, so we accept it here — but still enforce the
    per-token shape rules (no leading wildcard, >=3-char prefix) inside the phrase.
    """
    if not search_terms or not isinstance(search_terms, str):
        return

    # `*`/`?` inside a quoted phrase can't wildcard via query_string — run a
    # single word on the no-stem `.search.exact` field unquoted (#364), or keep it
    # inside a MULTI-word quoted phrase, which the engine supports via intervals: an
    # adjacency phrase `"smart* phone"` (ordered, max_gaps=0) or a proximity phrase
    # `"smart phone*"~N` (#355). (Don't say "move it outside the quotes": a bare
    # wildcard on the stemmed `.search` field is itself rejected by #364, so that
    # advice is now a dead end.)
    stripped = search_terms.strip()

    # Binary proximity `"A"~N~"B"` (oxjob #355 Goal B) -> intervals. Both operands and
    # their wildcards live in ONE intervals query, so validate every operand token and
    # apply the shared wildcard budget across BOTH operands. Handle it before the
    # per-phrase loop below, because that loop would see `"A"` (followed by `~N`) as a
    # proximity phrase but mis-classify the trailing `"B"` operand and wrongly reject it.
    mbin = BINARY_PROXIMITY_RE.match(stripped)
    if mbin:
        words = mbin.group(1).split() + mbin.group(3).split()
        for word in words:
            _validate_wildcard_token(word)
        _validate_wildcard_budget(words)
        return

    for phrase in QUOTED_PHRASE_RE.findall(search_terms):
        if "*" not in phrase and "?" not in phrase:
            continue
        # Proximity phrase `"…"~N` -> intervals (oxjob #355, L02c/PW7).
        if re.search(re.escape(f'"{phrase}"') + r"~\d", search_terms):
            for word in phrase.split():
                _validate_wildcard_token(word)
            _validate_wildcard_budget(phrase.split())
            continue
        # Adjacency phrase: the WHOLE search is a single multi-token quoted phrase
        # containing a wildcard (`"smart* phone"`) -> intervals ordered, max_gaps=0
        # (oxjob #355, Goal A). A single quoted wildcard token (`"studies*"`) is NOT
        # this path — #364 runs it unquoted on the no-stem field — so keep rejecting it.
        if stripped == f'"{phrase}"' and len(phrase.split()) >= 2:
            for word in phrase.split():
                _validate_wildcard_token(word)
            _validate_wildcard_budget(phrase.split())
            continue
        raise APIQueryParamsError(
            f'Wildcards (* or ?) do not work inside a quoted phrase: "{phrase}". '
            "For a single word, remove the quotes and use exact (no-stem) search; "
            'for a multi-word phrase use an adjacency phrase ("smart* phone") or '
            'proximity ("smart phone*"~3).'
        )

    # Outside quotes, check each whitespace-delimited token.
    unquoted = QUOTED_PHRASE_RE.sub(" ", search_terms)
    for word in unquoted.split():
        _validate_wildcard_token(word)


def validate_search_terms(search_terms):
    """Reject queries that combine many long quoted phrases with OR.

    Phrase queries on the works fulltext field have cost roughly proportional
    to phrase token count times posting-list length. A handful of long phrases
    OR'd together multiplies that cost across all clauses, which makes these
    queries disproportionately expensive on Elasticsearch. Bulk citation
    lookups should be issued as separate requests instead.

    Also rejects unsupported wildcard shapes (oxjob #337) so leading wildcards
    don't reach ES as a raw parse error and short-prefix wildcards don't silently
    degrade to a literal.
    """
    if not search_terms:
        return
    validate_wildcards(search_terms)
    long_phrases = [
        p for p in QUOTED_PHRASE_RE.findall(search_terms)
        if len(p) > LONG_PHRASE_CHAR_THRESHOLD
    ]
    if len(long_phrases) > MAX_LONG_PHRASES_IN_OR:
        raise APIQueryParamsError(
            f"This search combines more than {MAX_LONG_PHRASES_IN_OR} long "
            f"quoted phrases (>{LONG_PHRASE_CHAR_THRESHOLD} chars each) with "
            "OR. Lots of long-phrase OR searches are not supported. Try "
            "sending each phrase as a separate request."
        )


# Visually-similar Unicode punctuation that users paste from Word/web. Without
# folding these to ASCII, query-syntax detection (phrase quotes, booleans)
# is silently bypassed and exact-phrase searches degrade to keyword searches.
_SEARCH_INPUT_TRANSLATION = {
    # double-quote variants -> "
    0x201C: '"', 0x201D: '"', 0x201E: '"', 0x201F: '"',
    # single-quote / apostrophe variants -> ' (never a phrase delimiter here,
    # so children’s etc. stay intact)
    0x2018: "'", 0x2019: "'", 0x201A: "'", 0x201B: "'",
    # whitespace lookalikes -> regular space
    0x00A0: " ", 0x2002: " ", 0x2003: " ", 0x2004: " ", 0x2005: " ",
    0x2006: " ", 0x2007: " ", 0x2008: " ", 0x2009: " ", 0x200A: " ",
    0x202F: " ", 0x205F: " ", 0x3000: " ",
    # zero-width / invisible -> removed
    0x200B: None, 0x200C: None, 0x200D: None, 0xFEFF: None, 0x00AD: None,
}


def normalize_search_input(text):
    if not text or not isinstance(text, str):
        return text
    return text.translate(_SEARCH_INPUT_TRANSLATION)


class SearchOpenAlex:
    def __init__(
        self,
        search_terms,
        primary_field=None,
        secondary_field=None,
        tertiary_field=None,
        is_author_name_query=False,
        is_semantic_query=False,
        combine_fields=False,
    ):
        self.search_terms = normalize_search_input(search_terms)
        self.primary_field = primary_field if primary_field else "display_name"
        self.secondary_field = secondary_field
        self.tertiary_field = tertiary_field
        self.is_author_name_query = is_author_name_query
        self.is_semantic_query = is_semantic_query
        # When True, the Boolean/phrase/wildcard branch of primary_secondary_match_query
        # emits ONE query_string over a `fields` list instead of two OR'd query_strings,
        # so each Boolean operand can match in *either* field (cross-field). Used only by
        # title_and_abstract.search so its name finally matches its behavior (oxjob #191.7).
        self.combine_fields = combine_fields

    def build_query(self, skip_citation_boost=False):
        if not self.search_terms:
            return self.match_all()

        # Wildcard inside a quoted proximity phrase (`"smart phone*"~3`) — query_string
        # silently drops the wildcard, so build an ES `intervals` query instead (#355).
        if self.has_proximity_wildcard():
            raw_query = self.proximity_wildcard_query()
            if skip_citation_boost:
                return raw_query
            return self.citation_boost_query(raw_query)

        # Wildcard inside a multi-token quoted phrase WITHOUT proximity (`"smart* phone"`)
        # — adjacency; same `intervals` fix, ordered with max_gaps=0 (#355 Goal A).
        if self.has_adjacent_wildcard_phrase():
            raw_query = self.adjacent_wildcard_query()
            if skip_citation_boost:
                return raw_query
            return self.citation_boost_query(raw_query)

        # Binary proximity `"A"~N~"B"` — two separate operands NEAR each other (WoS
        # `NEAR/N`); `match_phrase`+slop can't express it (slop is whole-phrase), so it
        # builds an ES `intervals` query with one sub-interval per operand (#355 Goal B).
        # No wildcard required, but wildcards in either operand compose fine.
        if self.has_binary_proximity():
            raw_query = self.binary_proximity_query()
            if skip_citation_boost:
                return raw_query
            return self.citation_boost_query(raw_query)

        if (
            self.primary_field == "authorships.raw_affiliation_strings"
            and len(self.search_terms.strip()) > 3
        ):
            raw_query = self.query_string_query()
        elif self.is_author_name_query:
            raw_query = self.author_name_query()
        elif self.primary_field and self.secondary_field and self.tertiary_field:
            raw_query = self.primary_secondary_tertiary_match_query()
        elif self.primary_field and self.secondary_field:
            raw_query = self.primary_secondary_match_query()
        elif self.is_semantic_query:
            raw_query = self.semantic_query()
            if skip_citation_boost:
                return raw_query
            return self.citation_boost_query(raw_query, scaling_type="log")
        else:
            raw_query = self.primary_match_query()

        if skip_citation_boost:
            return raw_query
        return self.citation_boost_query(raw_query)

    @staticmethod
    def match_all():
        return Q("match_all")

    def query_string_query(self):
        return Q(
            "query_string",
            query=f"{self.search_terms}",
            default_operator="AND",
            default_field=self.primary_field,
            allow_leading_wildcard=False,
        ) | Q(
            "match_phrase",
            **{self.primary_field: {"query": self.search_terms, "boost": 2}},
        )

    def has_proximity_wildcard(self):
        """True for a single quoted proximity phrase containing a wildcard.

        e.g. `"smart phone*"~3` — the one shape where proximity and a wildcard compose.
        Plain proximity (`"smart phone"~3`) and plain wildcards stay on their existing
        paths; only the combination needs the `intervals` query (oxjob #355).
        """
        m = PROXIMITY_PHRASE_RE.match(self.search_terms.strip())
        return bool(m) and ("*" in m.group(1) or "?" in m.group(1))

    def has_adjacent_wildcard_phrase(self):
        """True for a single MULTI-token quoted phrase (no `~N`) containing a wildcard.

        e.g. `"smart* phone"` — adjacency: the tokens must appear in order with no gap
        between them, one of them a wildcard. It's the `ordered=true, max_gaps=0` sibling
        of the proximity case; query_string would silently drop the wildcard, so it also
        routes to an `intervals` query (oxjob #355, Goal A). A single quoted wildcard
        token (`"studies*"`) is NOT this path — #364 runs it unquoted on the no-stem
        field — so require >=2 tokens.
        """
        m = ADJACENT_PHRASE_RE.match(self.search_terms.strip())
        if not m:
            return False
        phrase = m.group(1)
        return ("*" in phrase or "?" in phrase) and len(phrase.split()) >= 2

    def has_binary_proximity(self):
        """True for binary proximity `"A"~N~"B"` (oxjob #355 Goal B).

        Two separate quoted operands joined by a slop, either of which may be a
        multi-word phrase (`"machine learning"~5~"neural network"`). Unlike the other
        intervals shapes this does NOT require a wildcard — it's a capability
        `match_phrase`+slop lacks entirely (slop loosens gaps within ONE phrase; it
        can't keep two phrases intact and search for them near each other).
        """
        return bool(BINARY_PROXIMITY_RE.match(self.search_terms.strip()))

    @staticmethod
    def _interval_rule(word):
        """Map one phrase token to an ES `intervals` rule.

        Trailing `*` -> `prefix` (cheap, anchored). Any other wildcard (mid-word `?`,
        embedded `*`) -> `wildcard`. A plain token -> `match` (so it's analyzed/stemmed
        consistently with the field). Shapes are pre-validated by validate_wildcards().
        """
        lower = word.lower()
        if word.endswith("*") and word.count("*") == 1 and "?" not in word:
            return {"prefix": {"prefix": lower[:-1]}}
        if "*" in word or "?" in word:
            return {"wildcard": {"pattern": lower}}
        return {"match": {"query": word}}

    def _intervals_over_fields(self, rule):
        """OR one `intervals` rule across primary (+secondary/+tertiary) fields.

        Mirrors the boost weights of the match-path branches. Shared by every
        intervals entry point (proximity, adjacency, binary proximity — oxjob #355).
        """
        fields = [(self.primary_field, None)]
        if self.secondary_field:
            fields.append((self.secondary_field, 0.10))
        if self.tertiary_field:
            fields.append((self.tertiary_field, 0.05))

        query = None
        for field, boost in fields:
            body = dict(rule)
            if boost is not None:
                body["boost"] = boost
            clause = Q("intervals", **{field: body})
            query = clause if query is None else (query | clause)
        return query

    def _intervals_query(self, phrase, ordered, max_gaps):
        """Build an ES `intervals` query for a single quoted wildcard phrase (#355).

        Each token becomes a match/prefix/wildcard rule; they are combined with
        `all_of` under the given `ordered`/`max_gaps`. Shared by the proximity
        (`"…"~N`, ordered=false) and adjacency (`"smart* phone"`,
        ordered=true/max_gaps=0) entry points.
        """
        rules = [self._interval_rule(w) for w in phrase.split()]
        rule = {"all_of": {"ordered": ordered, "max_gaps": max_gaps, "intervals": rules}}
        return self._intervals_over_fields(rule)

    def _operand_rule(self, phrase):
        """One binary-proximity operand -> an `intervals` rule (oxjob #355 Goal B).

        A single-word operand is just its match/prefix/wildcard rule; a multi-word
        operand (`"machine learning"`) becomes an ordered, gap-0 adjacency
        sub-interval so the phrase stays intact as a unit before the two operands are
        combined NEAR each other.
        """
        words = phrase.split()
        if len(words) == 1:
            return self._interval_rule(words[0])
        return {
            "all_of": {
                "ordered": True,
                "max_gaps": 0,
                "intervals": [self._interval_rule(w) for w in words],
            }
        }

    def proximity_wildcard_query(self):
        """Build an `intervals` query for `"phrase with wildcard*"~N` (oxjob #355).

        `ordered=false` + `max_gaps=N` reproduces OQL "within N words" (= WoS `W/n`,
        unordered NEAR); the spike pinned max_gaps==slop with no off-by-one.
        """
        m = PROXIMITY_PHRASE_RE.match(self.search_terms.strip())
        phrase, slop = m.group(1), int(m.group(2))
        return self._intervals_query(phrase, ordered=False, max_gaps=slop)

    def adjacent_wildcard_query(self):
        """Build an `intervals` query for `"smart* phone"` adjacency (oxjob #355 Goal A).

        `ordered=true` + `max_gaps=0` reproduces a quoted (exact/no-stem) phrase whose
        tokens are adjacent in order, one of them a wildcard — the no-`~N` analogue of a
        proximity phrase. Verified live on works-v33 (`"smart* phone"` = 4,986 hits vs
        plain `"smart phone"` = 4,975).
        """
        m = ADJACENT_PHRASE_RE.match(self.search_terms.strip())
        return self._intervals_query(m.group(1), ordered=True, max_gaps=0)

    def binary_proximity_query(self):
        """Build an `intervals` query for `"A"~N~"B"` binary proximity (#355 Goal B).

        Each operand is its own (possibly multi-word, adjacent) sub-interval; the two
        are combined `ordered=false` + `max_gaps=N` — unordered NEAR, matching OQL
        "within N words of" (= WoS `NEAR/N`) and consistent with the single-phrase
        proximity path's max_gaps==slop mapping (oxjob #355, pinned live on works-v33).
        """
        m = BINARY_PROXIMITY_RE.match(self.search_terms.strip())
        left, slop, right = m.group(1), int(m.group(2)), m.group(3)
        rule = {
            "all_of": {
                "ordered": False,
                "max_gaps": slop,
                "intervals": [self._operand_rule(left), self._operand_rule(right)],
            }
        }
        return self._intervals_over_fields(rule)

    def primary_match_query(self):
        """Searches with 'and' and phrase queries, with phrase boosted by 2."""
        if self.is_boolean_search() or self.has_phrase() or self.has_wildcard():
            self.clean_search_terms()
            return Q(
                "query_string",
                query=self.search_terms,
                default_field=self.primary_field,
                default_operator="AND",
                allow_leading_wildcard=False,
            )
        else:
            return Q(
                "match",
                **{self.primary_field: {"query": self.search_terms, "operator": "and"}},
            ) | Q(
                "match_phrase",
                **{self.primary_field: {"query": self.search_terms, "boost": 2}},
            )

    def primary_secondary_match_query(self):
        """Searches primary and secondary fields."""
        if self.is_boolean_search() or self.has_phrase() or self.has_wildcard():
            self.clean_search_terms()
            if self.combine_fields:
                # One query_string over both fields: ES expands each Boolean operand
                # (term or phrase) into a disjunction across the fields, so a Boolean
                # whose halves split across title↔abstract still matches. Preserves the
                # full query_string parser (phrases, wildcards, leading-wildcard disallow).
                # The `^0.1` keeps the secondary field's original 0.10 boost weight.
                return Q(
                    "query_string",
                    query=self.search_terms,
                    fields=[self.primary_field, f"{self.secondary_field}^0.1"],
                    default_operator="AND",
                    allow_leading_wildcard=False,
                )
            return Q(
                "query_string",
                query=self.search_terms,
                default_field=self.primary_field,
                default_operator="AND",
                allow_leading_wildcard=False,
            ) | Q(
                "query_string",
                query=self.search_terms,
                default_field=self.secondary_field,
                boost=0.10,
                default_operator="AND",
                allow_leading_wildcard=False,
            )
        else:
            return (
                Q(
                    "match",
                    **{
                        self.primary_field: {
                            "query": self.search_terms,
                            "operator": "and",
                            "boost": 1,
                        }
                    },
                )
                | Q(
                    "match_phrase",
                    **{self.primary_field: {"query": self.search_terms, "boost": 2}},
                )
                | Q(
                    "match",
                    **{
                        self.secondary_field: {
                            "query": self.search_terms,
                            "operator": "and",
                            "boost": 0.10,
                        }
                    },
                )
                | Q(
                    "match_phrase",
                    **{
                        self.secondary_field: {
                            "query": self.search_terms,
                            "boost": 0.15,
                        }
                    },
                )
            )

    def primary_secondary_tertiary_match_query(self):
        """Searches primary, secondary, tertiary fields."""
        if self.tertiary_field == "display_name_acronyms":
            tertiary_match_boost = 2
            tertiary_phrase_boost = 2
        else:
            tertiary_match_boost = 0.05
            tertiary_phrase_boost = 0.1

        if self.is_boolean_search() or self.has_phrase() or self.has_wildcard():
            self.clean_search_terms()
            return (
                Q(
                    "query_string",
                    query=self.search_terms,
                    default_field=self.primary_field,
                    default_operator="AND",
                    allow_leading_wildcard=False,
                )
                | Q(
                    "query_string",
                    query=self.search_terms,
                    default_field=self.secondary_field,
                    boost=0.5,
                    default_operator="AND",
                    allow_leading_wildcard=False,
                )
                | Q(
                    "query_string",
                    query=self.search_terms,
                    default_field=self.tertiary_field,
                    boost=tertiary_match_boost,
                    default_operator="AND",
                    allow_leading_wildcard=False,
                )
            )
        else:
            return (
                Q(
                    "match",
                    **{
                        self.primary_field: {
                            "query": self.search_terms,
                            "operator": "and",
                            "boost": 1.5,
                        }
                    },
                )
                | Q(
                    "match_phrase",
                    **{self.primary_field: {"query": self.search_terms, "boost": 3}},
                )
                | Q(
                    "match",
                    **{
                        self.secondary_field: {
                            "query": self.search_terms,
                            "operator": "and",
                            "boost": 0.3,
                        }
                    },
                )
                | Q(
                    "match_phrase",
                    **{
                        self.secondary_field: {
                            "query": self.search_terms,
                            "boost": 0.5,
                        }
                    },
                )
                | Q(
                    "match",
                    **{
                        self.tertiary_field: {
                            "query": self.search_terms,
                            "operator": "and",
                            "boost": tertiary_match_boost,
                        }
                    },
                )
                | Q(
                    "match_phrase",
                    **{
                        self.tertiary_field: {
                            "query": self.search_terms,
                            "boost": tertiary_phrase_boost,
                        }
                    },
                )
            )

    def author_name_query(self):
        """Search display_name and display_name.folded in order to ignore diacritics."""
        fields = [self.primary_field, self.primary_field + ".folded"]

        if self.secondary_field:
            fields.extend([self.secondary_field, self.secondary_field + ".folded"])

        most_fields_query = Q(
            "multi_match",
            query=self.search_terms,
            fields=fields,
            operator="and",
            type="most_fields",
        )

        phrase_query = Q(
            "multi_match",
            query=self.search_terms,
            fields=fields,
            type="phrase",
            boost=2,
        )

        return most_fields_query | phrase_query

    def semantic_query(self):
        query_vector = get_vector(self.search_terms)
        knn_query = KNNQuery("vector_embedding", query_vector, 100, similarity=0.5)
        return knn_query

    @staticmethod
    def citation_boost_query(query, scaling_type="sqrt"):
        """Uses cited_by_count to boost query results with a conditional script.
        Supports two types of scaling: 'sqrt' for square root, and 'log' for logarithmic scaling.
        """
        if scaling_type == "sqrt":
            script_source = """
            if (doc['cited_by_count'].size() == 0 || doc['cited_by_count'].value == 0) {
                return 0.5;
            } else {
                return 1 + Math.sqrt(doc['cited_by_count'].value);
            }
            """
        elif scaling_type == "log":
            script_source = """
            if (doc['cited_by_count'].size() == 0 || doc['cited_by_count'].value <= 1) {
                return 0.5;
            } else {
                return 1 + Math.log(doc['cited_by_count'].value);
            }
            """
        else:
            raise ValueError("Invalid scaling_type. Choose 'sqrt' or 'log'.")

        return Q(
            "function_score",
            functions=[{"script_score": {"script": {"source": script_source}}}],
            query=query,
            boost_mode="multiply",
        )

    def has_phrase(self):
        # search term contains two or more quotes
        return self.search_terms.count('"') >= 2

    def is_boolean_search(self):
        boolean_words = [" AND ", " OR ", " NOT "]
        return any(word in self.search_terms for word in boolean_words)

    def has_wildcard(self):
        """Detect intentional wildcard/fuzzy patterns in search terms.

        Matches (with minimum 3-character prefix to prevent expensive expansions):
        - * after 3+ word characters: machin*, chem*stry (but NOT a*, th*)
        - * before 3+ word characters: *machine (blocked by ES, but detected)
        - ? between two word characters only: wom?n (avoids 'therapy?' false positive)
        - ~ after 3+ word characters: term~2, machine~1 (but NOT a~2)
        - ~ after closing quote: "phrase"~5 (proximity search)
        """
        return bool(re.search(r'\w{3,}\*|\*\w{3,}|\w\?\w|\w{3,}~|"~', self.search_terms))

    def clean_search_terms(self):
        self.search_terms = (
            self.search_terms.strip()
            .replace("/", " ")
            .replace(":", " ")
            .replace("[", "")
            .replace("]", "")
        )
        if self.search_terms.lower().endswith(
            "and"
        ) or self.search_terms.lower().endswith("not"):
            self.search_terms = self.search_terms[:-3].strip()
        # strip html
        self.search_terms = self.search_terms.replace("<", "").replace(">", "")


def full_search_query(index_name, search_terms, skip_citation_boost=False):
    search_terms = normalize_search_input(search_terms)
    if index_name.lower().startswith("authors"):
        search_oa = SearchOpenAlex(
            search_terms=search_terms,
            secondary_field="display_name_alternatives",
            is_author_name_query=True,
        )
    elif index_name.lower().startswith("concepts"):
        search_oa = SearchOpenAlex(
            search_terms=search_terms, secondary_field="description"
        )
    elif index_name.lower().startswith("funders"):
        search_oa = SearchOpenAlex(
            search_terms=search_terms,
            secondary_field="alternate_titles",
            tertiary_field="description",
        )
    elif index_name.lower().startswith("awards"):
        search_oa = SearchOpenAlex(
            search_terms=search_terms,
            primary_field="display_name",
            secondary_field="description",
        )
        # Skip citation boost for awards since it doesn't have cited_by_count
        return search_oa.primary_secondary_match_query()
    elif index_name.lower().startswith("institutions"):
        search_oa = SearchOpenAlex(
            search_terms=search_terms,
            secondary_field="display_name_alternatives",
            tertiary_field="display_name_acronyms",
        )
    elif index_name.lower().startswith("publishers"):
        search_oa = SearchOpenAlex(
            search_terms=search_terms,
            secondary_field="alternate_titles",
        )
    elif index_name.lower().startswith("topics"):
        search_oa = SearchOpenAlex(
            search_terms=search_terms,
            secondary_field="description",
            tertiary_field="keywords",
        )
    elif index_name.lower().startswith("sources"):
        search_oa = SearchOpenAlex(
            search_terms=search_terms,
            secondary_field="alternate_titles",
            tertiary_field="abbreviated_title",
        )
    elif index_name.lower().startswith("works"):
        # Check if this is a span query for fulltext
        has_span = search_terms.upper().startswith('SPAN(')

        if has_span:
            # Parse and build span query for fulltext field
            import re
            match = re.match(r'SPAN\s*\(\s*"([^"]+)"\s*,\s*"([^"]+)"\s*,\s*(\d+)\s*\)', search_terms, re.IGNORECASE)
            if match:
                phrase1, phrase2, distance = match.groups()
                distance = int(distance)

                def build_span_clause(text):
                    words = text.split()
                    if len(words) == 1:
                        return {"span_term": {"fulltext": words[0].lower()}}
                    else:
                        return {
                            "span_near": {
                                "clauses": [{"span_term": {"fulltext": word.lower()}} for word in words],
                                "slop": 0,
                                "in_order": True
                            }
                        }

                return Q(
                    "span_near",
                    clauses=[
                        build_span_clause(phrase1),
                        build_span_clause(phrase2)
                    ],
                    slop=distance,
                    in_order=True
                )

        search_oa = SearchOpenAlex(
            search_terms=search_terms,
            secondary_field="abstract",
            tertiary_field="fulltext",
        )
    elif index_name.lower().startswith("funder-search"):
        # Support wildcards, proximity search, and span queries for funder-search
        # Proximity: "term1 term2"~5 finds terms within 5 words
        # Wildcards: fund* support*
        # Span: SPAN("phrase1", "term2", 10) finds phrase1 within 10 words of term2

        has_proximity = '~' in search_terms and '"' in search_terms
        has_wildcard = '*' in search_terms or '?' in search_terms
        has_span = search_terms.upper().startswith('SPAN(')

        if has_span:
            # Parse span query: SPAN("phrase1", "term2", distance)
            import re
            match = re.match(r'SPAN\s*\(\s*"([^"]+)"\s*,\s*"([^"]+)"\s*,\s*(\d+)\s*\)', search_terms, re.IGNORECASE)
            if match:
                phrase1, phrase2, distance = match.groups()
                distance = int(distance)

                # Helper function to build span clause for a phrase or term
                def build_span_clause(text):
                    words = text.split()
                    if len(words) == 1:
                        # Single term
                        return {"span_term": {"html": words[0].lower()}}
                    else:
                        # Multiple words - use span_near for the phrase
                        return {
                            "span_near": {
                                "clauses": [{"span_term": {"html": word.lower()}} for word in words],
                                "slop": 0,
                                "in_order": True
                            }
                        }

                # Build span near query
                return Q(
                    "span_near",
                    clauses=[
                        build_span_clause(phrase1),
                        build_span_clause(phrase2)
                    ],
                    slop=distance,
                    in_order=True
                )

        if has_proximity or has_wildcard:
            # Use query_string for advanced query support
            return Q(
                "query_string",
                query=search_terms,
                default_field="html",
                default_operator="AND",
            )
        else:
            search_oa = SearchOpenAlex(
                search_terms=search_terms,
                primary_field="html",
            )
            # Skip citation boost for funder-search since it doesn't have cited_by_count
            return search_oa.primary_match_query()
    else:
        search_oa = SearchOpenAlex(search_terms=search_terms)
    search_query = search_oa.build_query(skip_citation_boost=skip_citation_boost)
    return search_query


def full_search_query_exact(search_terms, skip_citation_boost=False):
    """Full search query for works using no_stem fields (no stemming)."""
    search_oa = SearchOpenAlex(
        search_terms=search_terms,
        primary_field="display_name.no_stem",
        secondary_field="abstract.no_stem",
        tertiary_field="fulltext.no_stem",
    )
    return search_oa.build_query(skip_citation_boost=skip_citation_boost)


def scoped_search_query(search_terms, scope, search_type, skip_citation_boost=False):
    """Build a search query scoped to specific fields.

    scope: "title" or "title_and_abstract"
    search_type: "default" (stemmed) or "exact" (no stemming)
    """
    is_exact = search_type == "exact"

    if scope == "title":
        field = "display_name.no_stem" if is_exact else "display_name"
        search_oa = SearchOpenAlex(
            search_terms=search_terms,
            primary_field=field,
        )
    elif scope == "title_and_abstract":
        primary = "display_name.no_stem" if is_exact else "display_name"
        secondary = "abstract.no_stem" if is_exact else "abstract"
        search_oa = SearchOpenAlex(
            search_terms=search_terms,
            primary_field=primary,
            secondary_field=secondary,
        )
    else:
        raise ValueError(f"Unknown search scope: {scope}")

    return search_oa.build_query(skip_citation_boost=skip_citation_boost)


def check_is_search_query(filter_params, search):
    search_keys = [
        "abstract.search",
        "abstract.search.exact",
        "default.search",
        "default.search.exact",
        "display_name.search",
        "display_name.search.exact",
        "fulltext.search",
        "fulltext.search.exact",
        "keyword.search",
        "raw_affiliation_strings.search",
        "raw_author_name.search",
        "semantic.search",
        "title.search",
        "title.search.exact",
        "title_and_abstract.search",
        "title_and_abstract.search.exact",
    ]

    if search and search != '""':
        return True

    if filter_params:
        for filter in filter_params:
            for key in search_keys:
                if filter.get(key, "") != "":
                    return True

    return False


def get_vector(text):
    """
    Use the minilm-l12-v2 model to get embeddings.
    """
    url = f"{ES_URL_WALDEN}/_ml/trained_models/sentence-transformers__all-minilm-l12-v2/_infer"
    data = {"docs": [{"text_field": text}]}
    response = requests.post(url, json=data)
    result = response.json()["inference_results"][0]["predicted_value"]
    return result
