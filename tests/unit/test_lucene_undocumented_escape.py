"""Undocumented Lucene operators become literal text on the query_string paths (oxjob #633, session 8).

help.openalex.org documents AND/OR/NOT, quotes, `~N` proximity/fuzzy and `*`/`?`
wildcards. ES `query_string` also honors `-`/`+` (token-leading prohibit/require),
`^N` (boost), `{a TO b}` (range) and `&&` — live only on the boolean / phrase /
wildcard branches of SearchOpenAlex, since the plain branch is analyzed (there
`+cancer -treatment` = `cancer treatment`, `machine^3 learning` = `machine 3
learning`; prod, 2026-08-22).

Measured over 7d of traffic, nobody uses them on purpose (0 deliberate boosts,
1 deliberate `-prohibit` per 30 days of hand-written queries), while ~3,800
req/wk of pasted titles with an uppercase AND/OR plus a spaced hyphen silently
EXCLUDE the paper they look up — openrepec's `title.search:MARKET -LEVEL
MEASURES … CONCEPTUAL AND EMPIRICAL …` = 0 as sent, 1 (the paper) escaped —
and `NOT -dog` 500s. Prod-verified escapes: `cancer AND \\-treatment` =
`cancer AND treatment` (1,815,982, vs 3,657,231 un-escaped); `\\{a TO b\\} AND
cancer` = 271,340 (vs 5,261,736, a live range query); `NOT \\-dog AND cancer` =
`NOT dog AND cancer`.

Asserts the emitted ES query shape via `.to_dict()` — no ES needed.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
sys.modules["settings"] = type(sys)("settings")
sys.modules["settings"].ES_URL_WALDEN = "http://localhost:9200"

from core.search import SearchOpenAlex, escape_undocumented_lucene  # noqa: E402


# --- the pure helper ------------------------------------------------------------

@pytest.mark.parametrize("raw,expected", [
    ("cancer AND -treatment", "cancer AND \\-treatment"),           # prohibit
    ("MARKET -LEVEL x AND y", "MARKET \\-LEVEL x AND y"),           # the openrepec shape
    ("NOT -dog", "NOT \\-dog"),                                     # 500s today
    ('-"machine learning" OR dog', '\\-"machine learning" OR dog'), # before a phrase
    ("(-a OR b) AND c", "(\\-a OR b) AND c"),                       # after an open paren
    ("cancer AND +treatment", "cancer AND \\+treatment"),           # require (a no-op anyway)
    ("machine^3 AND learning", "machine\\^3 AND learning"),         # boost
    ("a && b AND c", "a \\&\\& b AND c"),
    ("{a TO b} AND c", "\\{a TO b\\} AND c"),                       # range
    ("a - b AND c", "a \\- b AND c"),                               # lone dash
    ("", ""),
    (None, None),
])
def test_escapes_undocumented_operators_outside_quotes(raw, expected):
    assert escape_undocumented_lucene(raw) == expected


@pytest.mark.parametrize("raw", [
    '"n > 10^5" AND x',          # ^ inside quotes is already literal
    '"mean -7.6 to -1.2" OR y',  # - inside quotes
    "COVID-19 AND x",            # mid-token hyphen is one term to the parser
    "state-of-the-art OR y",
    "x AND C++",                 # mid-token plus
    "already \\-escaped AND z",  # user-escaped stays single-escaped
    '"a b"~3 AND c',             # documented proximity
    "machin* OR wom?n",          # documented wildcards
    "cancer~1 AND treatment",    # documented fuzzy
    "(a OR b) AND NOT c",        # documented boolean + grouping
])
def test_documented_syntax_and_literal_shapes_are_untouched(raw):
    assert escape_undocumented_lucene(raw) == raw


def test_unbalanced_trailing_quote_leaves_the_tail_alone():
    assert escape_undocumented_lucene('a AND "b -c') == 'a AND "b -c'


# --- wired into the builder -----------------------------------------------------

def _query_strings(q):
    """Every `query_string.query` in a built query, in order."""
    out = []

    def walk(node):
        if isinstance(node, dict):
            for k, v in node.items():
                if k == "query_string":
                    out.append(v["query"])
                walk(v)
        elif isinstance(node, list):
            for x in node:
                walk(x)
    walk(q.to_dict())
    return out


@pytest.mark.parametrize("kwargs", [
    dict(primary_field="display_name"),                                   # primary_match_query
    dict(primary_field="display_name", secondary_field="abstract"),       # 2-field, same-field
    dict(primary_field="display_name", secondary_field="abstract",
         combine_fields=True),                                            # 2-field, cross-field
    dict(primary_field="display_name", secondary_field="abstract",
         tertiary_field="fulltext"),                                      # 3-field
    dict(primary_field="display_name.no_stem", secondary_field="abstract.no_stem",
         tertiary_field="fulltext.no_stem", combine_fields=True),          # exact 3-field
])
def test_boolean_branch_query_string_carries_the_escaped_text(kwargs):
    q = SearchOpenAlex("cancer AND -treatment", **kwargs).build_query(skip_citation_boost=True)
    qs = _query_strings(q)
    assert qs, "boolean input must route to query_string"
    assert all(x == "cancer AND \\-treatment" for x in qs), qs


def test_phrase_branch_escapes_the_bare_tail():
    q = SearchOpenAlex('"machine learning" -neural', primary_field="display_name"
                       ).build_query(skip_citation_boost=True)
    assert _query_strings(q) == ['"machine learning" \\-neural']


def test_wildcard_branch_escapes_too():
    q = SearchOpenAlex("machin* -learning", primary_field="display_name.no_stem"
                       ).build_query(skip_citation_boost=True)
    assert _query_strings(q) == ["machin* \\-learning"]


def test_plain_branch_never_reaches_query_string_and_is_not_rewritten():
    """The analyzed path already treats these as punctuation; it must not be touched."""
    s = SearchOpenAlex("+cancer -treatment", primary_field="display_name",
                       secondary_field="abstract", combine_fields=True)
    q = s.build_query(skip_citation_boost=True)
    assert _query_strings(q) == []
    assert s.search_terms == "+cancer -treatment"


def test_raw_affiliation_query_string_path_is_escaped():
    q = SearchOpenAlex("Univ -Paris AND Sorbonne", primary_field="authorships.raw_affiliation_strings"
                       ).build_query(skip_citation_boost=True)
    assert _query_strings(q) == ["Univ \\-Paris AND Sorbonne"]


def test_intervals_paths_are_untouched():
    """#355 builders run before the query_string branches and never see the escape."""
    q = SearchOpenAlex('"smart* phone"~3', primary_field="display_name.no_stem"
                       ).build_query(skip_citation_boost=True)
    assert _query_strings(q) == []
    assert "intervals" in str(q.to_dict())
