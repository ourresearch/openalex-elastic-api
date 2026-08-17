"""#800 — wildcards on `raw affiliation` search, and coherent wildcard errors.

The ES field behind raw-affiliation search (`authorships.raw_affiliation_strings`)
is indexed WITHOUT stemming, so wildcards execute correctly on it (the classic
REST filter accepted them all along — 953,962 works for
`raw_affiliation_strings.search:process*`, prod 2026-08-17). But OQL keys wildcard
support off a registered `<base>.search.exact` sibling, which raw affiliation
lacked — so OQL rejected the wildcard with a self-contradicting error pair: the
unquoted branch said "quote the operand", the quoted branch said "remove the
wildcard" and blamed the ENTITY ("works has no exact search field" — false; it's
the column that had none). CNRS Q4c, 2026-08-17.

Fix: register `raw_affiliation_strings.search.exact` (same ES field; behaviorally
identical), and make the wildcard rejections check exact-availability FIRST (never
hint "quote it" when quoting can't help) and name the COLUMN the user typed.

    PYTHONPATH=. pytest tests/oql/test_raw_affiliation_wildcards.py -q
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


def _err(oql):
    with pytest.raises(Exception) as ei:
        L.parse(oql)
    return str(ei.value)


# ---- T-a: wildcards now work on raw affiliation ------------------------------

def test_simple_quoted_wildcard_parses_to_exact_column_and_round_trips():
    oqo = L.parse('works where raw affiliation has "process*"')
    assert [(f.column_id, f.value) for f in oqo.filter_rows] == [
        ("raw_affiliation_strings.search.exact", "process*")]
    rendered, identity = _rt('works where raw affiliation has "process*"')
    assert identity, rendered
    assert rendered == 'works where raw affiliation has ("process*")'


def test_nathalies_one_liner_parses_and_round_trips():
    q = ('works where raw affiliation has '
         '(within 50 ("process*", "material*", "solar", "font", "romeu"))')
    oqo = L.parse(q)
    assert [(f.column_id, f.value) for f in oqo.filter_rows] == [
        ("raw_affiliation_strings.search.exact",
         '"process*"~50~"material*"~"solar"~"font"~"romeu"')]
    rendered, identity = _rt(q)
    assert identity, rendered
    assert rendered == q


def test_plain_quoted_phrase_now_rides_the_exact_column():
    # No wildcard: quoted used to DEGRADE to the stemmed column (no exact sibling
    # existed); it now lands on .search.exact. Same ES field either way —
    # execution-identical — and it must still round-trip.
    oqo = L.parse('works where raw affiliation has "solar cells"')
    assert [f.column_id for f in oqo.filter_rows] == [
        "raw_affiliation_strings.search.exact"]
    rendered, identity = _rt('works where raw affiliation has "solar cells"')
    assert identity, rendered


def test_bare_stemmed_search_unchanged():
    oqo = L.parse("works where raw affiliation has (solar cells)")
    assert [f.column_id for f in oqo.filter_rows] == ["raw_affiliation_strings.search"]
    rendered, identity = _rt("works where raw affiliation has (solar cells)")
    assert identity, rendered
    assert rendered == "works where raw affiliation has (solar cells)"


# ---- T-b: the error circle is gone -------------------------------------------

def test_unquoted_wildcard_hint_now_actually_works_when_followed():
    # The "quote the operand" hint is only allowed when quoting HELPS — and on
    # raw affiliation it now does.
    msg = _err("works where raw affiliation has (within 50 (process*, material*))")
    assert "quote the operand" in msg
    L.parse('works where raw affiliation has (within 50 ("process*", "material*"))')


def test_unquoted_bare_wildcard_hint_works_when_followed():
    msg = _err("works where raw affiliation has process*")
    assert "quote it" in msg
    L.parse('works where raw affiliation has "process*"')


@pytest.mark.parametrize("quoted, unquoted", [
    ('works where raw author name has ("smith*")',
     "works where raw author name has (smith*)"),
    ('authors where display name has ("smith*")',
     "authors where display name has (smith*)"),
    ('works where raw author name has (within 3 ("smith*", "jones"))',
     "works where raw author name has (within 3 (smith*, jones))"),
])
def test_no_exact_column_gets_one_coherent_terminal_error(quoted, unquoted):
    # A column with NO exact sibling must give the SAME terminal error whether
    # the wildcard is quoted or not — never "quote it" -> "remove it" circles.
    m1, m2 = _err(quoted), _err(unquoted)
    for m in (m1, m2):
        assert "has no exact search variant" in m, m
        assert "remove the wildcard" in m, m
        assert "quote" not in m, m


def test_terminal_error_names_the_word_the_user_typed():
    # `raw author name` is an alias of the canonical word `byline`; the error
    # must echo what the user wrote, and name the entity after the column.
    msg = _err("works where raw author name has (smith*)")
    assert '"raw author name" has no exact search variant on works' in msg, msg
    msg = _err("works where byline has (smith*)")
    assert '"byline" has no exact search variant on works' in msg, msg
    msg = _err("authors where display name has (smith*)")
    assert '"display name" has no exact search variant on authors' in msg, msg


# ---- T-c: engine query targets the raw-affiliation ES field ------------------

def test_exact_param_builds_query_on_raw_affiliation_es_field():
    # Guard against the silent-dispatch trap: if the new param misses the
    # primary_field elif group in core/fields.py::SearchField.build_query, it
    # falls into the broad default full-search — wrong field, silently.
    from works.fields import fields_dict

    fld = fields_dict["raw_affiliation_strings.search.exact"]
    fld.value = "process*"
    q = str(fld.build_query().to_dict())
    assert "authorships.raw_affiliation_strings" in q, q

    fld = fields_dict["raw_affiliation_strings.search.exact"]
    fld.value = '"process*"~50~"material*"~"solar"'
    q = fld.build_query().to_dict()
    s = str(q)
    assert "intervals" in s, s
    assert "authorships.raw_affiliation_strings" in s, s
    assert "prefix" in s, s  # trailing-* operands become intervals prefix rules
