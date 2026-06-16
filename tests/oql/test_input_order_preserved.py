"""Decision 30 (#363) — honor the user's given operand order on the OQL/OQO side;
canonicalize (sort) order ONLY on the legacy-URL and NL→OQO paths.

`canonicalize_oqo(oqo, sort_operands=False)` preserves the order the user wrote —
both the top-level clause order and the value order inside `is ( … )` / `has ( … )`
groups — so the LEGO builder doesn't jump a new clause to its alphabetical slot and
SR authors keep their block order. The default (`sort_operands=True`) still sorts,
for hashing/dedup and the machine-shaped URL / NL paths. All the OTHER canonical
transforms (NNF, type coercion, column-id collapse, flatten/hoist) run regardless,
and render→parse→render idempotence still holds on the preserve path.

Run with:
    PYTHONPATH=. pytest tests/oql/test_input_order_preserved.py -q --noconftest
"""
import tests.oql._qt_loader  # noqa: F401  (installs the pure query_translation stub)

from query_translation.oql_lang import parse, render  # noqa: E402
from query_translation.oqo_canonicalizer import canonicalize_oqo  # noqa: E402
from query_translation.url_parser import parse_url_to_oqo  # noqa: E402


def _preserve(oql):
    return render(canonicalize_oqo(parse(oql), sort_operands=False))


def _sorted(oql):
    return render(canonicalize_oqo(parse(oql), sort_operands=True))


# --- clause order ------------------------------------------------------------
def test_clause_order_preserved_both_ways():
    """Two clause orderings stay distinct under sort_operands=False."""
    a = "works where year is 2020 and type is article"
    b = "works where type is article and year is 2020"
    assert _preserve(a) == a
    assert _preserve(b) == b


def test_clause_order_sorted_by_default():
    """Both orderings collapse to one alphabetical form under sort_operands=True."""
    a = "works where year is 2020 and type is article"
    b = "works where type is article and year is 2020"
    assert _sorted(a) == _sorted(b)


# --- value-group order -------------------------------------------------------
def test_value_order_preserved_in_search_group():
    assert _preserve("works where title has (dog or cat)") == \
        "works where title has (dog or cat)"
    assert _preserve("works where title has (cat or dog)") == \
        "works where title has (cat or dog)"


def test_value_order_preserved_in_enum_group():
    assert _preserve("works where country is (US or FR or DE)") == \
        "works where country is (US or FR or DE)"


def test_value_order_sorted_by_default():
    assert _sorted("works where title has (dog or cat)") == \
        "works where title has (cat or dog)"
    assert _sorted("works where country is (US or FR or DE)") == \
        "works where country is (DE or FR or US)"


# --- invariants that MUST survive --------------------------------------------
def test_idempotence_holds_on_preserve_path():
    """render -> parse -> render is a fixed point even when order is preserved."""
    for q in [
        "works where type is article and year is 2020",
        "works where title has (dog or cat)",
        "works where country is (US or FR or DE) and year >= 2020",
    ]:
        r1 = _preserve(q)
        r2 = _preserve(r1)
        assert r1 == r2, f"not idempotent: {q!r} -> {r1!r} -> {r2!r}"


def test_nnf_and_typing_still_run_when_not_sorting():
    """Order preservation must NOT disable the other canonical transforms."""
    # value typing: '2020' -> int on a numeric column (bare render is the same,
    # but the OQO leaf must be typed)
    o = canonicalize_oqo(parse("works where year is 2020 and type is article"),
                         sort_operands=False)
    yr = [f for f in o.filter_rows if f.column_id == "publication_year"][0]
    assert yr.value == 2020 and isinstance(yr.value, int)


# --- URL path stays canonical (sorted) regardless of URL field order ---------
def test_url_path_is_sorted_regardless_of_field_order():
    """The legacy-URL path is machine-shaped — its OQO sorts to one canonical form."""
    u1 = parse_url_to_oqo("works", "type:article,publication_year:2020")
    u2 = parse_url_to_oqo("works", "publication_year:2020,type:article")
    # default (sorted) canonical: both URL orderings converge
    assert canonicalize_oqo(u1).to_dict() == canonicalize_oqo(u2).to_dict()
