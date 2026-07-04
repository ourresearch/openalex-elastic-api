"""OQL operator precedence (#506).

Mixed `and`/`or` at one grouping level is no longer a loud error — it resolves by
the standard precedence **NOT > AND > OR** (the convention Web of Science, Scopus
since early 2026, boolean algebra, and every programming language use). The
canonical render always re-parenthesizes the grouping so the structure is never
left implicit on the page, and the round-trip stays exact.

See query_translation/oql_lang.py::_precedence_tree.
"""
from tests.oql.oql_v2 import parse, OQLError
from query_translation.oqo_canonicalizer import canonicalize_oqo
from query_translation.oql_lang import render


def rows(oql):
    return parse(oql).to_dict()["filter_rows"]


def canon(oql):
    """Canonical OQL text, user-order preserved (the OQL-text render path)."""
    return render(canonicalize_oqo(parse(oql), sort_operands=False))


# --- precedence at the top (between whole clauses) ---------------------------

def test_and_binds_tighter_than_or_between_clauses():
    # A and B or C  ==  (A and B) or C
    fr = rows("works where year is 2020 and title has cat or type is article")
    assert len(fr) == 1 and fr[0]["join"] == "or"
    kids = fr[0]["filters"]
    assert any(k.get("join") == "and" for k in kids)   # the A-and-B group
    assert any(k.get("column_id", "").startswith("type") for k in kids)  # bare C

    # A or B and C  ==  A or (B and C)
    fr = rows("works where year is 2020 or title has cat and type is article")
    assert fr[0]["join"] == "or"
    assert any(k.get("join") == "and" for k in fr[0]["filters"])


def test_two_and_groups_around_an_or():
    # A and B or C and D  ==  (A and B) or (C and D)
    fr = rows("works where year is 2020 and title has a "
              "or type is article and title has b")
    assert fr[0]["join"] == "or"
    ands = [k for k in fr[0]["filters"] if k.get("join") == "and"]
    assert len(ands) == 2


def test_pure_and_and_pure_or_stay_flat():
    # no mixing -> a single flat level, no nested groups, no error
    fr = rows("works where year is 2020 and title has a and type is article")
    assert all("join" not in k for k in fr)  # flat AND (implicit top-level)
    fr = rows("works where year is 2020 or title has a or type is article")
    assert len(fr) == 1 and fr[0]["join"] == "or"
    assert all("join" not in k for k in fr[0]["filters"])


def test_not_binds_tightest():
    # not A or B  ==  (not A) or B  — NOT is a prefix operator, tightest
    fr = rows("works where not type is article or type is book")
    assert fr[0]["join"] == "or"
    negated = [k for k in fr[0]["filters"] if k.get("is_negated")]
    assert len(negated) == 1 and negated[0]["value"] == "article"


# --- precedence inside a value / search group -------------------------------

def test_precedence_inside_value_group():
    # country is (US and GB or FR)  ==  (US and GB) or FR
    fr = rows("works where country is (US and GB or FR)")
    assert len(fr) == 1 and fr[0]["join"] == "or"
    assert any(k.get("join") == "and" for k in fr[0]["filters"])


def test_precedence_inside_search_group_with_implicit_and():
    # title has (a b or c)  — the space-run `a b` is one AND unit; mixing with
    # the explicit `or` resolves to  (a-b) or c  (no error).
    fr = rows("works where title has (climate change or warming)")
    assert fr[0]["join"] == "or"
    # explicit and mixed with or, too
    fr = rows("works where title has (climate and change or warming)")
    assert fr[0]["join"] == "or"
    assert any(k.get("join") == "and" for k in fr[0]["filters"])


def test_mixed_bool_never_raises():
    # the whole point: none of these throw OQL_MIXED_BOOL_NEEDS_PARENS anymore
    for q in [
        "works where year is 2020 and title has cat or type is article",
        "works where country is (US and GB or FR)",
        "works where title has (a and b or c)",
    ]:
        parse(q)  # must not raise


# --- canonical render always parenthesizes the precedence grouping ----------

def test_canonical_adds_parens_for_the_and_group():
    assert canon("works where year is 2020 and title has cat or type is article") \
        == "works where (year is (2020) and title has (cat)) or type is (article)"
    assert canon("works where year is 2020 or title has cat and type is article") \
        == "works where year is (2020) or (title has (cat) and type is (article))"


def test_canonical_keeps_pure_levels_paren_free():
    assert canon("works where year is 2020 and title has a and type is article") \
        == "works where year is (2020) and title has (a) and type is (article)"
    assert canon("works where year is 2020 or title has a or type is article") \
        == "works where year is (2020) or title has (a) or type is (article)"


# --- round-trip is exact ----------------------------------------------------

def test_roundtrip_is_stable():
    for q in [
        "works where year is 2020 and title has cat or type is article",
        "works where year is 2020 or title has cat and type is article",
        "works where country is (US and GB or FR)",
        "works where title has (climate and change or warming)",
    ]:
        once = canon(q)
        twice = canon(once)
        assert once == twice, f"{q!r}: {once!r} != {twice!r}"


def test_unparenthesized_input_matches_its_parenthesized_canonical():
    # parsing the original and parsing its (parenthesized) canonical give the
    # same OQO tree — precedence and explicit parens converge.
    q = "works where year is 2020 and title has cat or type is article"
    a = canonicalize_oqo(parse(q)).to_dict()
    b = canonicalize_oqo(parse(canon(q))).to_dict()
    assert a == b
