"""Known-bug tests for negation shapes that currently parse-but-wrong (#432).

These are DELIBERATE red tests, not skips: each documents a negation form the
parser accepts today but resolves incorrectly. They fail until #363 fixes the
behavior, at which point they go green (and then guard against regression).

Per Jason (2026-06-13): a corpus case passes fully or it doesn't exist — no
skipped/xfail placeholder rows. So these live OUTSIDE the corpus (not rows in
corpus.yaml) as standalone failing tests, and the assertion is written to be
**resolution-independent**: it holds whether #363 ends up (a) parsing the idiom
correctly OR (b) rejecting it with a loud diagnostic. Either fix turns these
green; only the current silent mis-parse fails them.

Full write-up + the open parse-vs-reject decision:
  oxjobs working/oql-systematic-reviews/work/NEGATION_PROBLEM_SPACE.md
"""
from tests.oql.oql_v2 import parse, OQLError
from query_translation.oqo_canonicalizer import canonicalize_oqo


def _leaves(node):
    """Yield every leaf filter dict under an OQO filter node (groups nest via
    `filters`)."""
    if isinstance(node, dict) and "filters" in node:
        for child in node["filters"]:
            yield from _leaves(child)
    else:
        yield node


def _positive_leaf_values(oql):
    """Parse `oql` and return the values of every POSITIVE (non-negated) leaf.

    If the parser rejects the query (a loud diagnostic — one acceptable fix),
    return None to signal "no positive leaves to worry about"."""
    try:
        oqo = canonicalize_oqo(parse(oql)).to_dict()
    except OQLError:
        return None  # rejected loudly == an acceptable resolution
    vals = []
    for row in oqo.get("filter_rows", []):
        for leaf in _leaves(row):
            if not leaf.get("is_negated"):
                vals.append(str(leaf.get("value", "")))
    return vals


def test_compact_bang_phrase_excludes_not_includes():
    """zd#8101 WoS within-value NOT idiom: `England!"New England"` means
    "England AND NOT the exact phrase New England". The excluded phrase must
    NEVER survive as a POSITIVE search term.

    Currently mis-parses to a single positive leaf `England! New England`, so
    "New England" is positively REQUIRED — the opposite of the intent. Fails
    until #432/#363 either parse it as `England and not "New England"` (New
    England becomes a negated leaf) or reject it (parse raises). See
    NEGATION_PROBLEM_SPACE.md."""
    vals = _positive_leaf_values(
        'works where title/abstract contains (England!"New England")'
    )
    if vals is None:
        return  # parser rejected it — acceptable fix
    offending = [v for v in vals if "New England" in v]
    assert not offending, (
        "the excluded phrase 'New England' leaked into a POSITIVE leaf "
        f"{offending!r} — the within-value `!` NOT operator mis-parses "
        "(it should be a negated leaf, or the query should be rejected)."
    )
