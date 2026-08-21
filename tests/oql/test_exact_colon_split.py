"""A colon in a bare `.search.exact` value must not block the token split (oxjob #633, session 6).

`:` used to sit in `_EXACT_SPLIT_BANNED_RE` as the Lucene FIELD separator, so
`split_exact_words` refused to split any value containing one and the oql leg
fell back to the quoted-phrase render — a different query. Scholarly titles are
full of colons ("Beyond Data Gaps: Tracking …"), which made this the single
largest cause of a lossy echo: ~6.3% of all `.exact` traffic (prod-measured,
Cloudflare AE 7d, 2026-08-21), vs 1.1% for the exotic Lucene tail.

The ban was over-cautious. Prod-measured on `title_and_abstract.search.exact`:

    learning machine        2,919,096   AND-of-words baseline
    learning: machine       2,919,096   colon analyzed away as punctuation
    learning : machine      2,919,096   ditto
    display_name:cancer             0   field syntax does NOT resolve here
    split into two leaves   2,919,096   the split is result-preserving

So the colon is ordinary punctuation to this door and splitting is safe. The
remaining chars (`" ( ) | [ ] , ; ~ ^ ! &`) genuinely change the result set and
stay banned — `machine^3 learning` = 229,590 vs 2,919,096 unboosted.

Pure: no app boot. Run with
    PYTHONPATH=. pytest tests/oql/test_exact_colon_split.py -q --noconftest
"""
import pytest

import tests.oql._qt_loader  # noqa: F401  (installs the pure query_translation stub)

from query_translation.oqo import BranchFilter  # noqa: E402
from query_translation.oql_lang import split_exact_words  # noqa: E402
from query_translation.oql_parser import parse_oql_to_oqo  # noqa: E402
from query_translation.oql_renderer import render_oqo_to_oql  # noqa: E402
from query_translation.url_parser import parse_url_to_oqo  # noqa: E402
from query_translation.url_renderer import render_oqo_to_url  # noqa: E402

COL = "title_and_abstract.search.exact"
PARAM = "search.title_and_abstract.exact"


def _scoped(value):
    return parse_url_to_oqo("works", scoped_searches={PARAM: value})


def _leaf_values(oqo):
    return [(f.column_id, f.value, bool(getattr(f, "is_negated", False)))
            for f in oqo.filter_rows]


def _rows(oqo):
    """Comparable snapshot of the filter tree, for round-trip assertions."""
    return oqo.to_dict()["filter_rows"]


# --- the splitter itself ------------------------------------------------------

@pytest.mark.parametrize("value,expected", [
    ("learning machine", ["learning", "machine"]),          # control, no colon
    ("learning: machine", ["learning:", "machine"]),         # trailing colon
    ("foo:bar machine", ["foo:bar", "machine"]),             # colon mid-token
    ("learning : machine", ["learning", ":", "machine"]),    # colon-only token
    ("Beyond Data Gaps: Tracking",
     ["Beyond", "Data", "Gaps:", "Tracking"]),               # real title shape
])
def test_colon_does_not_block_the_split(value, expected):
    assert split_exact_words(value) == expected


def test_single_token_with_colon_still_does_not_split():
    """One token is one leaf regardless of punctuation — nothing to AND."""
    assert split_exact_words("learning:") is None


@pytest.mark.parametrize("value", [
    "machine^3 learning",       # boost — changes the result set (229,590 vs 2,919,096)
    "machine~2 learning",       # fuzzy
    '+cancer -treatment',       # require/prohibit
    'the "big" thing',          # quotes would re-parse as syntax
    "cancer|treatment",         # OR-pipe is split upstream, not here
    "a [b TO c]",               # range brackets
    "Windows AND DLL",          # uppercase Lucene operator word
])
def test_genuinely_structural_values_still_refuse_to_split(value):
    assert split_exact_words(value) is None


# --- parse: a colon value canonicalizes to per-token leaves -------------------

def test_scoped_param_with_colon_parses_to_per_token_leaves():
    oqo = _scoped("learning: machine")
    assert _leaf_values(oqo) == [
        (COL, "learning:", False),
        (COL, "machine", False),
    ]


def test_real_colon_title_parses_to_per_token_leaves():
    oqo = _scoped("Beyond Data Gaps: Tracking")
    assert [v for _, v, _ in _leaf_values(oqo)] == [
        "Beyond", "Data", "Gaps:", "Tracking",
    ]


def test_filter_door_agrees_with_the_scoped_param_door():
    """Every entry door must produce the ONE canonical OQO for the same intent."""
    assert _rows(_scoped("learning: machine")) == _rows(
        parse_url_to_oqo("works", filter_string=f"{COL}:learning: machine"))


# --- render + round-trip: both legs survive the colon -------------------------

COLON_CASES = [
    ("control, no colon", "learning machine"),
    ("trailing colon", "learning: machine"),
    ("colon mid-token", "foo:bar machine"),
    ("colon-only token", "learning : machine"),
    ("real title", "Beyond Data Gaps: Tracking"),
]


@pytest.mark.parametrize("label,value", COLON_CASES, ids=[c[0] for c in COLON_CASES])
def test_url_leg_round_trips(label, value):
    """The rendered `filter=` must re-parse to the identical tree — i.e. the
    clause splitter's `,(?=<col>:)` lookahead is not fooled by a value colon."""
    oqo = _scoped(value)
    filter_string = render_oqo_to_url(oqo)["filter"]
    assert _rows(parse_url_to_oqo("works", filter_string=filter_string)) == _rows(oqo)


@pytest.mark.parametrize("label,value", COLON_CASES, ids=[c[0] for c in COLON_CASES])
def test_oql_leg_round_trips(label, value):
    oqo = _scoped(value)
    assert _rows(parse_oql_to_oqo(render_oqo_to_oql(oqo))) == _rows(oqo)


def test_oql_render_is_the_faithful_and_of_quoted_tokens():
    """The whole point: the oql leg is the AND-of-words, not a quoted phrase.

    Before the fix this rendered `has ("learning: machine")` — the phrase,
    which re-executes to 23,661 instead of 2,919,096 (prod, −99.2%).
    """
    assert render_oqo_to_oql(_scoped("learning: machine")) == (
        'works where title/abstract has ("learning:" and "machine")')


def test_colon_bearing_token_keeps_its_colon_verbatim():
    """No stripping/escaping — the user's text stays byte-stable through the echo."""
    oqo = _scoped("Beyond Data Gaps: Tracking")
    assert "Gaps:" in [v for _, v, _ in _leaf_values(oqo)]
    assert "Gaps:" in render_oqo_to_url(oqo)["filter"]
    assert '"Gaps:"' in render_oqo_to_oql(oqo)


# --- negation: colon values ride the Cat-1 De Morgan path too -----------------

def test_negated_colon_value_de_morgans_to_or_of_negated_leaves():
    oqo = parse_url_to_oqo("works", filter_string=f"{COL}:!learning: machine")
    rows = oqo.filter_rows
    assert len(rows) == 1 and isinstance(rows[0], BranchFilter)
    assert rows[0].join == "or"
    assert [(f.value, f.is_negated) for f in rows[0].filters] == [
        ("learning:", True), ("machine", True),
    ]


def test_negated_colon_value_round_trips_on_both_legs():
    oqo = parse_url_to_oqo("works", filter_string=f"{COL}:!learning: machine")
    assert render_oqo_to_url(oqo)["filter"] == f"{COL}:!learning: machine"
    assert _rows(parse_oql_to_oqo(render_oqo_to_oql(oqo))) == _rows(oqo)
    assert render_oqo_to_oql(oqo) == (
        'works where title/abstract has (not "learning:" or not "machine")')


# --- the comma+colon shape session 5 flagged as a possible blocker ------------

def test_comma_and_colon_in_one_value_is_normalized_then_split():
    """A token can never carry BOTH a colon and a comma: session 2's comma
    normalization turns commas into spaces at the door, before the split.
    `Review:, methods` therefore behaves as `Review: methods`."""
    oqo = _scoped("Review:, methods")
    assert [v for _, v, _ in _leaf_values(oqo)] == ["Review:", "methods"]
    filter_string = render_oqo_to_url(oqo)["filter"]
    assert _rows(parse_url_to_oqo("works", filter_string=filter_string)) == _rows(oqo)
    assert _rows(parse_oql_to_oqo(render_oqo_to_oql(oqo))) == _rows(oqo)
