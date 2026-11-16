"""Boolean precedence NOT > AND > OR in search strings (oxjob #1050). No ES.

Lucene's classic parser (ES query_string) has no precedence: `a AND b OR c` became
`+a b c` and `a OR b AND c` became `a +b +c`, so terms beside an OR were silently
dropped while the echo (`meta.x_query.oql`) said they ran. The live before/after is in
the oxjob's work/ receipts (ZD 4409)."""
import json

import pytest

from core import keyword_search as ks
from core.search import (
    SearchOpenAlex,
    clean_query_string_text,
    scoped_search_query,
    works_keyword_search_query,
)
from core.search_precedence import explicit_boolean_precedence as group

REWRITES = [
    # ZD 4409, queries 5 and 6
    (
        '"life" AND "cycle" AND "sustainability" AND "assessment" OR "lcsa"',
        '("life" AND "cycle" AND "sustainability" AND "assessment") OR "lcsa"',
    ),
    (
        '"life" AND "cycle" AND "sustainability" AND "asdsaddsadasd" OR "lcsdasasdasda"',
        '("life" AND "cycle" AND "sustainability" AND "asdsaddsadasd") OR "lcsdasasdasda"',
    ),
    ("a OR b AND c", "a OR (b AND c)"),
    ("a AND b OR c AND d", "(a AND b) OR (c AND d)"),
    # Words side by side are one AND-group (OQL spec: a run of bare words is one node).
    ("climate change OR warming", "(climate change) OR warming"),
    ("kelp urchin OR otter", "(kelp urchin) OR otter"),
    # NOT binds tightest, inside its AND-group.
    ("kelp OR urchin NOT otter", "kelp OR (urchin NOT otter)"),
    ("kelp NOT urchin OR otter", "(kelp NOT urchin) OR otter"),
    ("urchin OR NOT kelp", "urchin OR (NOT kelp)"),
    ("NOT dog OR cat", "(NOT dog) OR cat"),
    # Inside a group, and a group as one operand.
    ("(a AND b OR c) AND d", "((a AND b) OR c) AND d"),
    ("(a OR b) c OR d", "((a OR b) c) OR d"),
    ("a OR NOT (b OR c)", "a OR (NOT (b OR c))"),
    # Phrases, proximity, wildcards and fuzziness are single operands.
    ('"heart failure" AND diet OR "salt intake"', '("heart failure" AND diet) OR "salt intake"'),
    ('"smart phone"~3 AND use OR tablet', '("smart phone"~3 AND use) OR tablet'),
    ('"smart"~3~"phone" AND use OR tablet', '("smart"~3~"phone" AND use) OR tablet'),
    ("machin* learn OR deep~1", "(machin* learn) OR deep~1"),
    # Spacing is kept: only parentheses are added.
    ("a  AND\tb   OR c", "(a  AND\tb)   OR c"),
    # An escaped parenthesis is text.
    (r"a\(b OR c d", r"a\(b OR (c d)"),
]

UNCHANGED = [
    "",
    None,
    "cat",
    "a OR b OR c",
    "a AND b NOT c",
    "a b c",
    "NOT dog",
    "NOT dog cat",
    "(a OR b) AND c",
    "a OR (b AND c)",
    '"rock OR roll"',
    '"rock OR roll" AND jazz',
    '"a b"~3 OR c',
    "a OR \"b c\"",
    "ORCID OR",  # dangling operator: left for _trim_dangling / ES
    "a OR",
    "OR a",
    "a OR OR b",
    "(a OR b AND c",  # unbalanced: left alone
    "a OR b AND c)",
    '"a OR b AND c',
    "a || b c",
    'foo"bar" OR baz qux',
    "a or b and c",  # lowercase words are words, not operators
]


@pytest.mark.parametrize("raw,expected", REWRITES)
def test_groups_and_before_or(raw, expected):
    assert group(raw) == expected


@pytest.mark.parametrize("raw,expected", REWRITES)
def test_only_parentheses_are_added(raw, expected):
    assert group(raw).replace("(", "").replace(")", "") == raw.replace("(", "").replace(")", "")


@pytest.mark.parametrize("raw", [r for r, _ in REWRITES] + [u for u in UNCHANGED if u])
def test_idempotent(raw):
    assert group(group(raw)) == group(raw)


@pytest.mark.parametrize("raw", UNCHANGED)
def test_unchanged(raw):
    assert group(raw) == raw


def test_deep_nesting_is_left_alone():
    deep = "(" * 3000 + "a OR b c" + ")" * 3000
    assert group(deep) == deep


def test_cleaning_writes_the_grouping():
    assert clean_query_string_text("a OR b AND c") == "a OR (b AND c)"
    # Dangling operators go first, then the grouping.
    assert clean_query_string_text("a AND b OR c AND") == "(a AND b) OR c"
    # Escaping still sees a token start after the new parenthesis.
    assert clean_query_string_text("a OR -b c") == r"a OR (\-b c)"


def _query_strings(d):
    found = []

    def walk(node):
        if isinstance(node, dict):
            if "query_string" in node:
                found.append(node["query_string"]["query"])
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(d)
    return found


@pytest.mark.parametrize("scope", ["title", "title_and_abstract"])
def test_scoped_search_runs_the_grouping(scope):
    q = '"life" AND "cycle" AND "sustainability" AND "assessment" OR "lcsa"'
    d = scoped_search_query(q, scope, "default", skip_citation_boost=True).to_dict()
    assert _query_strings(d) and all(
        s == '("life" AND "cycle" AND "sustainability" AND "assessment") OR "lcsa"'
        for s in _query_strings(d)
    )


def test_broad_search_runs_the_grouping(monkeypatch):
    monkeypatch.setattr(ks, "lookup", lambda spans: {})
    ks.keyword_record.cache_clear()
    d = works_keyword_search_query("kelp OR urchin AND otter", with_fulltext=True,
                                   skip_citation_boost=True).to_dict()
    assert set(_query_strings(d)) == {"kelp OR (urchin AND otter)"}
    ks.keyword_record.cache_clear()


def test_keyword_alternatives_still_apply_to_a_grouped_search(monkeypatch):
    kw = {"remote work": ["https://openalex.org/keywords/remote-work"]}
    monkeypatch.setattr(ks, "lookup", lambda spans: {s: list(kw.get(s.lower(), [])) for s in spans})
    ks.keyword_record.cache_clear()
    d = scoped_search_query('"remote work" AND burnout OR stress', "title_abstract_keywords", "default",
                            skip_citation_boost=True).to_dict()
    text = json.dumps(d)
    assert 'keywords.id:\\"https://openalex.org/keywords/remote-work\\"' in text
    assert any(s.startswith('(("remote work" OR keywords.id:') and s.endswith(") OR stress")
               for s in _query_strings(d))
    ks.keyword_record.cache_clear()


def test_semantic_and_plain_searches_are_untouched():
    plain = SearchOpenAlex("climate change", primary_field="display_name")
    assert plain.build_query(skip_citation_boost=True).to_dict() == SearchOpenAlex(
        "climate change", primary_field="display_name"
    ).build_query(skip_citation_boost=True).to_dict()
    assert "query_string" not in json.dumps(plain.build_query(skip_citation_boost=True).to_dict())
