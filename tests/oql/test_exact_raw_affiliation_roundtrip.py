"""#799 — the keyword `raw_affiliation_strings` column ("exact raw affiliation",
whole-string equality) must render as ITSELF and round-trip.

Before the fix, `_build_by_column()` tier 0 claimed `_BY_COLUMN[<search base id>]`
for every curated search Field, so the bare id `raw_affiliation_strings` — which
is ALSO a distinct, non-search engine column — was owned by the SEARCH word
"raw affiliation". An equality leaf on it rendered `raw affiliation is (X)`,
which does not re-parse (search fields take `has`), trapping GUI users in a
validate → search → invalid loop (CNRS Q4b, 2026-08-17).

    PYTHONPATH=. pytest tests/oql/test_exact_raw_affiliation_roundtrip.py -q
"""
import pytest

from query_translation import oql_lang as L
from query_translation.oqo_canonicalizer import canonicalize_oqo


def _rt(oql):
    """parse → canonicalize → render → parse → canonicalize; return (rendered, same?)."""
    start = canonicalize_oqo(L.parse(oql))
    rendered = L.render(start)
    back = canonicalize_oqo(L.parse(rendered))
    return rendered, start.to_dict() == back.to_dict()


# ---- T-a: the bug ------------------------------------------------------------

@pytest.mark.parametrize("oql", [
    'works where exact raw affiliation is "DYNAVIR"',
    'works where raw_affiliation_strings is "DYNAVIR"',
    'works where year is (2024) and exact raw affiliation is (DYNAVIR or "Foo Bar")',
    'works where raw affiliation has (DYNAVIR) and exact raw affiliation is not (DYNAVIR)',
])
def test_exact_raw_affiliation_renders_itself_and_round_trips(oql):
    rendered, identity = _rt(oql)
    assert identity, rendered
    assert "exact raw affiliation is" in rendered, rendered
    assert "raw affiliation is" not in rendered.replace("exact raw affiliation is", ""), rendered


def test_exact_raw_affiliation_parses_to_keyword_column():
    oqo = L.parse('works where exact raw affiliation is "DYNAVIR"')
    assert [(f.column_id, f.value) for f in oqo.filter_rows] == [
        ("raw_affiliation_strings", "DYNAVIR")]
    assert L.render(oqo) == "works where exact raw affiliation is (DYNAVIR)"


# ---- T-b: search renders unchanged ------------------------------------------

@pytest.mark.parametrize("oql", [
    "works where raw affiliation has (DYNAVIR)",
    "works where title has (cats)",
    "works where full text has (x)",
    "works where abstract has (x)",
    "works where byline has (smith)",
])
def test_search_words_still_render_themselves(oql):
    rendered, identity = _rt(oql)
    assert rendered == oql
    assert identity


def test_search_and_exact_coexist():
    rendered, identity = _rt(
        "works where raw affiliation has (DYNAVIR) and exact raw affiliation is (DYNAVIR)")
    assert identity
    assert "raw affiliation has (DYNAVIR)" in rendered
    assert "exact raw affiliation is (DYNAVIR)" in rendered


# ---- T-c: class guard, structural -------------------------------------------

def _distinct_nonsearch_works_columns():
    from core.properties import get_entity_properties
    works = get_entity_properties("works")
    return {cid for cid, p in works.items()
            if "search" not in set(getattr(p, "operators", []) or [])}


def test_search_fields_claim_their_full_ids_and_never_shadow_a_distinct_column():
    distinct = _distinct_nonsearch_works_columns()
    for _spellings, fld in L._FIELDS:
        if fld.kind != "search":
            continue
        assert L._BY_COLUMN.get(fld.column + ".search") is fld, fld.column
        if fld.column in distinct:
            owner = L._BY_COLUMN.get(fld.column)
            assert owner is None or owner.kind != "search", (
                f"{fld.column!r} is a distinct non-search column but renders as the "
                f"search word {owner.oql!r} — equality leaves would not round-trip")


def test_the_two_known_collisions_are_exactly_these():
    # If this set grows, add the new column to T-d's coverage (or an allowlist).
    assert L._distinct_nonsearch_columns() == {"raw_affiliation_strings", "display_name"}


# ---- T-d: class guard, behavioral -------------------------------------------

# Columns whose fallback words ("title", "display_name") CANNOT parse with `is`
# because a curated alias of a SEARCH field shadows them at parse time — so
# their equality leaves are only reachable from URL→OQO and never round-trip
# through OQL text in either direction (pre-existing; documented in oxjob #799).
_KNOWN_UNPARSEABLE_COLUMNS = {"display_name"}


def _works_is_words():
    idx = L._entity_fallback("works")
    out = []
    for word, fld in sorted(idx.items()):
        if fld.kind not in ("string", "num") or fld.column in _KNOWN_UNPARSEABLE_COLUMNS:
            continue
        out.append((word, fld))
    return out


@pytest.mark.parametrize("word,fld", _works_is_words(),
                         ids=[w for w, _ in _works_is_words()])
def test_every_works_is_word_round_trips(word, fld):
    val = "1" if fld.kind == "num" else '"x"'
    oql = f"works where {word} is {val}"
    try:
        start = canonicalize_oqo(L.parse(oql))
    except L.OQLError as e:
        pytest.fail(f"{oql!r} does not parse ({e}); if this is a curated-alias shadow, "
                    f"add {fld.column!r} to _KNOWN_UNPARSEABLE_COLUMNS with a reason")
    rendered = L.render(start)
    back = canonicalize_oqo(L.parse(rendered))
    assert start.to_dict() == back.to_dict(), f"{oql!r} -> {rendered!r} does not round-trip"
