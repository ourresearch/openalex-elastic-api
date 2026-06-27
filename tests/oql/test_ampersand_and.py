"""`&` is an accepted INPUT synonym for `and` (oxjob #363).

It parses identically to `and` everywhere a connective is legal (clause body and
inside a `has ( … )` search group), and it is input-only: the canonical render
always spells out `and`, never `&`.
"""
from query_translation.oql_lang import parse, render


def _oqo(oql):
    return parse(oql).to_dict()


def test_ampersand_equals_and_in_clause_body():
    assert _oqo("works where year is 2020 & type is article") == \
        _oqo("works where year is 2020 and type is article")


def test_ampersand_equals_and_in_search_group():
    assert _oqo('works where title has (cats & dogs)') == \
        _oqo('works where title has (cats and dogs)')


def test_ampersand_respects_precedence():
    # `&` is AND, so it binds tighter than `or` exactly like the spelled-out word.
    assert _oqo("works where year is 2020 & (type is article or type is review)") == \
        _oqo("works where year is 2020 and (type is article or type is review)")


def test_ampersand_never_in_canonical_render():
    out = render(parse("works where year is 2020 & type is article"))
    assert "&" not in out
    assert " and " in out
