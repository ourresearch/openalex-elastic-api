"""Search text reaches ES query_string cleaned on every path, raw affiliation strings
included (oxjob #1889).

Live on 27 Oct 2026, before this fix: raw_affiliation_strings.search answered HTTP 500 for
`/`, `[ ]`, `:` at an edge, a trailing `\\`, a quote or parenthesis with no partner and an
operator with nothing to join (25 of 47 probes; 38 of 995 sampled real affiliation
strings), because query_string_query skipped clean_search_terms. Every other .search filter
500'd on `cancer AND (research`, `cancer AND "research` and `cancer AND research\\`, and
clean_search_terms cut a trailing "and"/"not" by suffix, so `"breast cancer" Finland` ran
as `... Finl` (0 results instead of 238).

Asserts the emitted query text via `.to_dict()`; no ES needed. Spacing inside the cleaned
text is not part of the contract (the parser ignores it), so most cases compare words.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
sys.modules.setdefault("settings", type(sys)("settings"))
sys.modules["settings"].ES_URL_WALDEN = "http://localhost:9200"

from core.search import (  # noqa: E402
    SearchOpenAlex,
    clean_query_string_text,
    pair_parens,
    pair_quotes,
)
from tests.unit.test_lucene_undocumented_escape import _query_strings  # noqa: E402

RAW_AFF = "authorships.raw_affiliation_strings"


def _words(text):
    return " ".join(text.split())


# --- quotes and parentheses with no partner ---------------------------------------

@pytest.mark.parametrize("raw,expected", [
    ('cancer "research', "cancer research"),                  # phrase never closed
    ('JSC "NMZ "ISKRA"', 'JSC "NMZ ISKRA"'),                   # inner quote can't close
    # A title whose curly quote normalize_search_input made straight, inside an OR-list
    # of quoted titles (the client that retried every 12 s).
    ('"A b" OR "Putting the "Visual Back in QA" OR "C d"',
     '"A b" OR "Putting the Visual Back in QA" OR "C d"'),
    ('"breast cancer" Finland "x', '"breast cancer" Finland x'),
    ('"a b", c "d', '"a b", c d'),                             # a comma may follow a closer
])
def test_pair_quotes_repairs_an_odd_count(raw, expected):
    assert _words(pair_quotes(raw)) == expected


@pytest.mark.parametrize("raw", [
    '"breast cancer" AND "heart failure"',
    '"a"b',                     # even count: ES reads it, so it is left as typed
    'say \\"hello',             # an escaped quote is text already
    "no quotes at all",
])
def test_pair_quotes_leaves_paired_or_escaped_quotes(raw):
    assert pair_quotes(raw) == raw


@pytest.mark.parametrize("raw,expected", [
    ("Hunan Agricultural University,Changsha 410128)", "Hunan Agricultural University,Changsha 410128"),
    ("cancer AND (research", "cancer AND research"),
    ("(a OR b) AND (c OR d", "(a OR b) AND c OR d"),
    ("a) AND (b", "a AND b"),
    ('"Lab (A" AND b', '"Lab (A" AND b'),                     # inside quotes: text already
    ("(a OR b) AND c", "(a OR b) AND c"),
    ("x \\( y", "x \\( y"),                                    # escaped
])
def test_pair_parens(raw, expected):
    assert _words(pair_parens(raw)) == expected


# --- the whole cleaner --------------------------------------------------------------

@pytest.mark.parametrize("raw,expected", [
    ("Wellcome Institute/Cancer Research UK", "Wellcome Institute Cancer Research UK"),
    ("Dept. of Physics [Lab A]", "Dept. of Physics Lab A"),
    ("University: Physics", "University Physics"),
    ("http://www.example.org/physics", "http www.example.org physics"),
    ("cancer research\\", "cancer research"),
    ("cancer research \\\\", "cancer research"),
    ("cancer\\ AND", "cancer"),                               # a backslash exposed by a later step
    ("cancer\\ )", "cancer"),
    ('cancer\\ "', "cancer"),
    ("cancer OR", "cancer"),
    ("cancer AND NOT", "cancer"),
    ("AND cancer", "cancer"),
    ("OR AND cancer", "cancer"),
    ("OR cancer AND", "cancer"),
    ("cancer and", "cancer"),                                  # the old rule's own case
    ("cancer or", "cancer or"),                                # lowercase or is a word to ES
    ("<i>Drosophila</i> AND melanogaster", "Drosophila AND melanogaster"),
    ("<sup>1</sup>Department of Physics", "1 Department of Physics"),
    ("x < 5 AND y > 3", "x 5 AND y 3"),                        # not a tag: nothing between is lost
    ("cancer AND -treatment", "cancer AND \\-treatment"),      # #633 escaping still applies
])
def test_clean_query_string_text(raw, expected):
    assert _words(clean_query_string_text(raw)) == expected


@pytest.mark.parametrize("raw", ["AND", "AND OR NOT", "\\"])
def test_nothing_left_is_sent_as_typed_for_es_to_reject(raw):
    # Elasticsearch rejects it and app.py answers a JSON 400 (core/user_query_errors.py).
    assert clean_query_string_text(raw) == raw


def test_inner_spacing_is_kept():
    # keyword_search adds keywords to a Boolean only when the cleaned text equals the typed text.
    assert clean_query_string_text("heart  AND\tfailure") == "heart  AND\tfailure"


@pytest.mark.parametrize("word", [
    "Finland", "England", "Thailand", "Switzerland", "Maryland", "Zealand", "island",
    "hand", "demand", "understand", "cannot", "knot", "Pinot", "Land", "Brand",
])
def test_a_word_ending_in_and_or_not_keeps_its_letters(word):
    # Used to be cut by suffix: Finland -> Finl, cannot -> can.
    assert clean_query_string_text(f'"breast cancer" {word}') == f'"breast cancer" {word}'
    assert clean_query_string_text(f"cancer AND {word}") == f"cancer AND {word}"


@pytest.mark.parametrize("raw", [
    '"breast cancer" AND (screening OR mammography)',
    "(a OR b) AND NOT c",
    '"heart failure"~5 AND drug',
    "machin* OR wom?n",
    "cancer~1 AND treatment",
    "NOT dog AND cat",
])
def test_documented_syntax_is_untouched(raw):
    assert clean_query_string_text(raw) == raw


def test_long_operator_runs_stay_fast():
    # A backtracking regex took 74 ms on 8 KB of `and and ...`; the token trim is linear.
    import time
    raw = "x " + "and " * 2000 + "x"
    started = time.perf_counter()
    clean_query_string_text(raw)
    clean_query_string_text(raw.rstrip("x"))
    assert time.perf_counter() - started < 0.05


# --- wired into the builders ---------------------------------------------------------

@pytest.mark.parametrize("raw,expected", [
    ("Wellcome Institute/Cancer Research UK", "Wellcome Institute Cancer Research UK"),
    ("Dept. of Physics [Lab A]", "Dept. of Physics Lab A"),
    ("INSERM U123/CNRS", "INSERM U123 CNRS"),
    ("Department of Navigation,Dalian Naval Academy,Dalian116018,China)",
     "Department of Navigation,Dalian Naval Academy,Dalian116018,China"),
    ("Physics [Lab", "Physics Lab"),
    ("cancer:", "cancer"),
    ('JSC "NMZ "ISKRA"', 'JSC "NMZ ISKRA"'),
    ("University of Oxford, Oxford, England", "University of Oxford, Oxford, England"),
])
def test_raw_affiliation_query_string_is_cleaned(raw, expected):
    q = SearchOpenAlex(raw, primary_field=RAW_AFF).build_query(skip_citation_boost=True)
    assert [_words(x) for x in _query_strings(q)] == [expected]
    # The phrase half is analyzed, so it keeps the string as pasted.
    phrase = q.to_dict()["bool"]["should"][1]["match_phrase"][RAW_AFF]["query"]
    assert phrase == SearchOpenAlex(raw, primary_field=RAW_AFF).search_terms


@pytest.mark.parametrize("kwargs", [
    dict(primary_field="display_name"),
    dict(primary_field="display_name", secondary_field="abstract", combine_fields=True),
    dict(primary_field="display_name.no_stem", secondary_field="abstract.no_stem",
         tertiary_field="fulltext.no_stem", combine_fields=True),
])
@pytest.mark.parametrize("raw,expected", [
    ("cancer AND (research", "cancer AND research"),
    ('cancer AND "research', "cancer AND research"),
    ("cancer AND research\\", "cancer AND research"),
    ('"breast cancer" Finland', '"breast cancer" Finland'),
])
def test_boolean_and_phrase_branches_are_cleaned(kwargs, raw, expected):
    q = SearchOpenAlex(raw, **kwargs).build_query(skip_citation_boost=True)
    qs = _query_strings(q)
    assert qs and all(_words(x) == expected for x in qs), qs
