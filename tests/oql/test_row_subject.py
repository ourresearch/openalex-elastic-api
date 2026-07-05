"""#557 — row-subject verb-phrase leaves: `it cites (…)` / `it's cited by (…)`.

A grammar CATEGORY (pronoun-subject predicates), not a one-off: the subject is
the queried row itself — the pronoun `it` — and a verb phrase names a relation
column; the value is the usual parenthesized group.

  it cites (W…)          -> referenced_works   (the row cites W)
  it's cited by (W…)     -> cited_by           (the row is in W's reference list)
  it's related to (W…)   -> related_to

Locked here:
  1. Canonical renders (contraction included) are fixed points.
  2. Forgiving input: `it is …`, `its …` (dropped apostrophe), and every legacy
     field-word form (`cites is`, `references is`, `cited by is`, `related to
     is`, raw column ids) converge on the canonical renders.
  3. Negation is VALUE-LEVEL ONLY (decision 23): `it cites (not W)`; there is
     no `doesn't`/`isn't` verb form (OQL_BAD_VERB_PHRASE).
  4. `it` is reserved at the clause slot; a lone `it` in a search VALUE stays an
     ordinary term (only a COMPLETE verb phrase opens a clause).
  5. oxurl frozen: `filter=referenced_works:` / `cited_by:` / `related_to:` —
     `cites:` is never rendered.
  6. Word unification: referenced_works's display word is "cites" (column/sort
     surfaces); the filter leaf renders via the verb form, never `cites is`.
"""
import pytest

from tests.oql.oql_v2 import parse, render, OQLError
from query_translation.oqo_canonicalizer import canonicalize_oqo
from query_translation.oqo import canonicalize_oqo_column_ids


def _canon(oql):
    return canonicalize_oqo(canonicalize_oqo_column_ids(parse(oql)))


def _render(oql):
    return render(_canon(oql))


# ---------------------------------------------------------------------------
# 1+2. Canonical renders are fixed points; forgiving input converges.
# ---------------------------------------------------------------------------
CONVERGE = [
    # (input, canonical render)
    ("works where it cites (W123)", "works where it cites (W123)"),
    ("works where cites is (W123)", "works where it cites (W123)"),
    ("works where references is (W123)", "works where it cites (W123)"),
    ("works where referenced_works is (W123)", "works where it cites (W123)"),
    ("works where it's cited by (W123)", "works where it's cited by (W123)"),
    ("works where it is cited by (W123)", "works where it's cited by (W123)"),
    ("works where its cited by (W123)", "works where it's cited by (W123)"),
    ("works where cited by is (W123)", "works where it's cited by (W123)"),
    ("works where cited_by is (W123)", "works where it's cited by (W123)"),
    ("works where it's related to (W123)", "works where it's related to (W123)"),
    ("works where it is related to (W123)", "works where it's related to (W123)"),
    ("works where related to is (W123)", "works where it's related to (W123)"),
    ("works where related_to is (W123)", "works where it's related to (W123)"),
    # bare verb forms (EXPLORE decision 6): the field word IS the verb, so a
    # value group directly after it implies `is` — row-subject columns only.
    ("works where cites (W123)", "works where it cites (W123)"),
    ("works where cited by (W123)", "works where it's cited by (W123)"),
    ("works where related to (W123)", "works where it's related to (W123)"),
    ("works where references (W123)", "works where it cites (W123)"),
    ("works where cites (not W123)", "works where it cites (not W123)"),
    # curly apostrophe (U+2019) — macOS/iOS smart punctuation auto-curls `it's`
    ("works where it’s cited by (W123)", "works where it's cited by (W123)"),
    ("works where it’s related to (W123)", "works where it's related to (W123)"),
]


def test_bare_verb_form_is_row_subject_only():
    # the implied-`is` allowance must not leak to ordinary fields
    with pytest.raises(OQLError) as e:
        parse("works where year (2020)")
    assert e.value.code == "OQL_MISSING_OPERATOR"


@pytest.mark.parametrize("inp,want", CONVERGE, ids=[c[0] for c in CONVERGE])
def test_input_converges_on_canonical(inp, want):
    out = _render(inp)
    assert out == want
    assert _render(out) == out          # the canonical form is a fixed point


def test_oqo_columns_are_the_frozen_oxurl_params():
    oqo = _canon("works where it cites (W1) and it's cited by (W2) "
                 "and it's related to (W3)").to_dict()
    cols = sorted(f["column_id"] for f in oqo["filter_rows"])
    assert cols == ["cited_by", "referenced_works", "related_to"]


# ---------------------------------------------------------------------------
# 3. Negation: value-level only; no verb-level form.
# ---------------------------------------------------------------------------
def test_value_level_not_roundtrips():
    out = _render("works where it cites (not W123)")
    assert out == "works where it cites (not W123)"
    assert _render(out) == out


@pytest.mark.parametrize("bad", [
    "works where it doesn't cite (W123)",
    "works where it does not cite (W123)",
    "works where it isn't cited by (W123)",
    "works where it is (W123)",           # copula with no verb phrase
    "works where it's cites (W123)",      # contraction + copula-less verb
    "works where it cited by (W123)",     # missing copula
    "works where it",
])
def test_no_verb_level_negation_or_partial_phrase(bad):
    with pytest.raises(OQLError) as e:
        parse(bad)
    assert e.value.code == "OQL_BAD_VERB_PHRASE"


# ---------------------------------------------------------------------------
# 4. `it` claims the clause slot only as a COMPLETE verb phrase; inside a
#    search value it stays an ordinary term.
# ---------------------------------------------------------------------------
def test_it_as_search_term_untouched():
    assert _render("works where title has (it)") == "works where title has (it)"
    # (canonicalizer value-sorts the group — the point is `it` stays a term)
    assert (_render("works where title has (rain and it)")
            == "works where title has (it and rain)")


def test_row_subject_breaks_a_bare_value_run():
    # after `and`, a complete verb phrase starts a new clause — not a second
    # undelimited value (the D1 arity guard must see through it)
    out = _render("works where year is 2020 and it cites (W123)")
    assert out == "works where year is (2020) and it cites (W123)"


def test_verb_phrase_in_prose_stays_a_loud_undelimited_error():
    # a verb phrase NOT followed by `(` inside a bare term run must not
    # silently manufacture an id filter from prose — the D1 loud error wins
    with pytest.raises(OQLError) as e:
        parse("works where title has rain and it cites wonder")
    assert e.value.code == "OQL_UNDELIMITED_TERM_LIST"


# ---------------------------------------------------------------------------
# 5. Composition: any position in the chain, OR-lists, merged same-column leaves.
# ---------------------------------------------------------------------------
def test_composes_anywhere():
    # (clause order below is the canonicalizer's deterministic sort — the point
    # is the leaf parses in first/mid/last position and renders the verb form)
    assert (_render("works where title has (climate) and it cites (W123)")
            == "works where title has (climate) and it cites (W123)")
    out = _render("works where it cites (W123) and year is (2020)")
    assert "it cites (W123)" in out and "year is (2020)" in out
    assert _render(out) == out


def test_or_list_and_same_column_merge():
    assert (_render("works where it cites (W1 or W2)")
            == "works where it cites (W1 or W2)")
    # decision 20: same-column leaves merge into one factored verb clause
    assert (_render("works where it cites (W1) and it cites (W2)")
            == "works where it cites (W1 and W2)")


def test_unknown_value_rides_the_verb_form():
    out = _render("works where it cites (unknown)")
    assert out == "works where it cites (unknown)"
    assert _render(out) == out


# ---------------------------------------------------------------------------
# 6. v2 render (builder token stream) matches the canonical text — including
#    the FACTORED verb clause, which v2 builds via its own eq path (the bug
#    this locks: v2 emitted `cites is (…)` while format_oql said `it cites (…)`).
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("q", [
    "works where it cites (W1)",
    "works where it cites (W1 and W2)",              # factored path
    "works where it's cited by (not W1 or W2)",      # factored + negation
])
def test_v2_lines_match_canonical(q):
    from query_translation.oql_render_v2 import render_v2
    oqo = _canon(q)
    r = render_v2(oqo)
    joined = " ".join("".join(t["text"] for t in ln["tokens"])
                      for ln in r["lines"]).strip()
    assert joined == render(oqo)
    # the chip label is the BARE verb; the col token text is the pronoun
    clause = r["where"]
    if clause["node"] == "clause":
        assert clause["column"] in ("cites", "cited by", "related to")
        col_toks = [t for ln in r["lines"] for t in ln["tokens"]
                    if t["t"] == "col"]
        assert col_toks and col_toks[0]["text"] in ("it", "it's")
