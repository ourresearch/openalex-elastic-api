"""#554 — a condition's value is ALWAYS a parenthesized group in canonical OQL.

Three rule changes, one job:
  1. Canonical render wraps EVERY condition value in `( … )` (zero exceptions);
     bare singletons remain accepted input (the lenient layer, asserted here —
     the corpus records only canonical forms, regen_corpus_oql.py rewrites them).
  2. Bare space-adjacency between values in an `is ( … )` group is a LOUD error
     (`OQL_GROUP_VALUES_NEED_CONNECTIVE`), never a silent implicit AND. The
     `has ( … )` run-merge (D2 reversal, #363) is untouched.
  3. Scalar-domain operators (comparisons, booleans, collection, semantic) take
     exactly ONE atom in their group (`OQL_GROUP_NEEDS_ONE_VALUE`), and
     `unknown` inside a group is the null sentinel.
"""
import pytest

from tests.oql.oql_v2 import parse, render, OQLError
from query_translation.oqo_canonicalizer import canonicalize_oqo


def _canon(oql):
    return canonicalize_oqo(parse(oql)).to_dict()


def _render(oql):
    return render(canonicalize_oqo(parse(oql)))


# ---------------------------------------------------------------------------
# 1. The lenient layer: bare singleton input -> parenthesized canonical, with
#    identical OQO either way. One case per condition-operator surface.
# ---------------------------------------------------------------------------
LENIENT = [
    # (bare input, parenthesized input, canonical render)
    ("works where type is article",
     "works where type is (article)",
     "works where type is (article)"),
    ("works where institution is I136199984",
     "works where institution is (I136199984)",
     "works where institution is (I136199984)"),
    ("works where title has cancer",
     "works where title has (cancer)",
     "works where title has (cancer)"),
    ('works where title has "climate change"',
     'works where title has ("climate change")',
     'works where title has ("climate change")'),
    ("works where year >= 2019",
     "works where year >= (2019)",
     "works where year >= (2019)"),
    ("works where date <= 2020-12-31",
     "works where date <= (2020-12-31)",
     "works where date <= (2020-12-31)"),
    ("works where open access is true",
     "works where open access is (true)",
     "works where open access is (true)"),
    ("works where language is unknown",
     "works where language is (unknown)",
     "works where language is (unknown)"),
    ("works where work is in collection col_abc123",
     "works where work is in collection (col_abc123)",
     "works where work is in collection (col_abc123)"),
    ('works where abstract is similar to "quantum computing"',
     'works where abstract is similar to ("quantum computing")',
     'works where abstract is similar to ("quantum computing")'),
]


@pytest.mark.parametrize("bare,parened,canonical", LENIENT,
                         ids=[c[0].split("where ")[1][:28] for c in LENIENT])
def test_bare_singleton_accepted_and_canonicalizes_to_parens(bare, parened, canonical):
    assert _canon(bare) == _canon(parened), "bare and parened input must be one OQO"
    assert _render(bare) == canonical
    # idempotence: the canonical form is its own canonical form
    assert _render(canonical) == canonical


def test_negation_canonicalizes_inside_the_group():
    # `is not X` (predicate sugar) and `is (not X)` (canonical) are one OQO.
    assert _canon("works where country is not FR") == \
        _canon("works where country is (not FR)")
    assert _render("works where country is not FR") == \
        "works where country is (not FR)"
    assert _render("works where language is not unknown") == \
        "works where language is (not unknown)"
    assert _render("works where work is in collection not col_abc123") == \
        "works where work is in collection (not col_abc123)"
    # booleans fold instead: never a rendered `not`
    assert _render("works where open access is (not true)") == \
        "works where open access is (false)"


# ---------------------------------------------------------------------------
# 2. Implicit AND between is-group values is dead (Part 1).
# ---------------------------------------------------------------------------
def test_is_group_bare_adjacency_is_a_loud_error():
    with pytest.raises(OQLError) as exc:
        parse("works where type is (article review)")
    assert exc.value.code == "OQL_GROUP_VALUES_NEED_CONNECTIVE"
    assert "or" in exc.value.fixit


def test_is_group_adjacency_error_fires_in_nested_groups():
    with pytest.raises(OQLError) as exc:
        parse("works where country is (FR or (US GB))")
    assert exc.value.code == "OQL_GROUP_VALUES_NEED_CONNECTIVE"


def test_is_not_group_adjacency_also_errors():
    with pytest.raises(OQLError) as exc:
        parse("works where type is not (article review)")
    assert exc.value.code == "OQL_GROUP_VALUES_NEED_CONNECTIVE"


def test_explicit_connectives_in_value_groups_still_work():
    # D7: explicit `and` between values is deliberate and stays. The top-level
    # AND flattens into filter_rows (canonical NNF / implicit top-level AND).
    got = _canon("works where country is (us and uk)")
    assert sorted(f["value"] for f in got["filter_rows"]) == ["UK", "US"]
    # `or` groups unchanged
    got = _canon("works where type is (article or review)")
    assert got["filter_rows"][0]["join"] == "or"


def test_recover_mode_collects_the_adjacency_error():
    from tests.oql.oql_v2 import parse_collecting
    oqo, errs = parse_collecting("works where type is (article review)")
    assert any(e.code == "OQL_GROUP_VALUES_NEED_CONNECTIVE" for e in errs)


def test_has_side_run_merge_untouched():
    # A bare-word run in a has-group is ONE stemmed node (D2 reversal) — the
    # new error must never fire on the search side.
    got = _canon("works where title has (mental health)")
    leaf = got["filter_rows"][0]
    assert leaf["value"] == "mental health"
    got = _canon("works where title has (climate change or warming)")
    assert got["filter_rows"][0]["join"] == "or"


# ---------------------------------------------------------------------------
# 3. Scalar domains: exactly one atom in the group; unknown = null sentinel.
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("oql", [
    "works where year >= (2019 or 2020)",
    "works where retracted is (true or false)",
    "works where work is in collection (col_a or col_b)",
    'works where abstract is similar to ("a" or "b")',
])
def test_scalar_domain_groups_take_exactly_one_atom(oql):
    with pytest.raises(OQLError) as exc:
        parse(oql)
    assert exc.value.code == "OQL_GROUP_NEEDS_ONE_VALUE"


def test_year_is_group_still_takes_many_atoms():
    # The arity rule bites the COMPARISON surface, not `is` on a num column.
    got = _canon("works where year is (2019 or 2020)")
    assert got["filter_rows"][0]["join"] == "or"


def test_unknown_in_group_is_null_sentinel():
    got = _canon("works where language is (unknown)")
    leaf = got["filter_rows"][0]
    assert leaf["value"] is None
    assert _canon("works where language is (unknown)") == \
        _canon("works where language is unknown")


def test_mixed_group_with_unknown_is_expressible():
    got = _canon("works where language is (en or unknown)")
    branch = got["filter_rows"][0]
    assert branch["join"] == "or"
    assert sorted([f["value"] for f in branch["filters"]],
                  key=lambda v: (v is None, v)) == ["en", None]
    out = _render("works where language is (en or unknown)")
    assert out == "works where language is (en or unknown)"
    # negated sentinel inside a group
    got = _canon("works where language is (en or not unknown)")
    vals = {(f["value"], f.get("is_negated", False)) for f in got["filter_rows"][0]["filters"]}
    assert (None, True) in vals
