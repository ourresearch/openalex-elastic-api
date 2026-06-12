"""OQL `return` clause (oxjob #450 Phase 3) — parser, renderer, round-trips.

`return col1, col2` is the OQL surface of `OQO.select`. It resolves over the
COLUMN namespace (the `column` capability / `?select=`-able result fields), a
mostly-disjoint namespace from the filter columns the `where` clause resolves —
so these tests cover schema-only columns (`open_access`, `authorships`) that no
filter clause can name, alongside both-namespace ones (`publication_year`).
"""
import pytest

from query_translation.oql_lang import parse, render, OQLError
from query_translation.oqo import OQO
from query_translation.validator import OQOValidator
from core.properties import ENTITY_PROPERTIES, get_entity_columns


# --------------------------------------------------------------------------- #
# Parsing
# --------------------------------------------------------------------------- #
def test_return_raw_column_ids():
    oqo = parse("works return id, doi, publication_year")
    assert oqo.select == ["id", "doi", "publication_year"]


def test_return_friendly_names_resolve_to_column_ids():
    oqo = parse("works return id, title, cited by count")
    assert oqo.select == ["id", "title", "cited_by_count"]


def test_return_schema_only_columns():
    # open_access / authorships are result columns with NO filter surface —
    # they must resolve via the column namespace, not _parse_field.
    oqo = parse("works return open_access, authorships")
    assert oqo.select == ["open_access", "authorships"]
    # and via their friendly display names
    oqo2 = parse("works return open access, authorships")
    assert oqo2.select == ["open_access", "authorships"]


def test_return_order_is_preserved():
    oqo = parse("works return cited_by_count, id, doi")
    assert oqo.select == ["cited_by_count", "id", "doi"]


def test_return_composes_with_other_directives():
    oqo = parse("works where year >= 2020 sort by year desc "
                "group by type sample 100 return id, title")
    assert oqo.select == ["id", "title"]
    assert oqo.sample == 100
    assert [s.column_id for s in oqo.sort_by] == ["publication_year"]
    assert [g.column_id for g in oqo.group_by] == ["type"]


def test_return_before_other_directives_also_parses():
    # directive order is free on input; canonical render puts return last
    oqo = parse("works return id sort by year desc")
    assert oqo.select == ["id"]
    assert oqo.sort_by[0].column_id == "publication_year"


def test_return_on_non_works_entities():
    assert parse("authors return id, display_name, works count").select == \
        ["id", "display_name", "works_count"]
    assert parse("sources return id, issn").select == ["id", "issn"]


def test_return_keyword_ends_where_expression():
    oqo = parse("works where type is article return id")
    assert oqo.select == ["id"]
    assert len(oqo.filter_rows) == 1


def test_return_unknown_word_passes_through_for_validator():
    # mirrors _parse_sort_field: unknown words flow to the validator's
    # column-capability gate rather than failing the parse
    oqo = parse("works return bogus_column")
    assert oqo.select == ["bogus_column"]
    res = OQOValidator().validate(oqo)
    assert not res.valid
    assert any(e.type == "invalid_select_column" for e in res.errors)


def test_return_with_no_column_errors():
    with pytest.raises(OQLError) as exc:
        parse("works return")
    assert exc.value.code == "OQL_BAD_RETURN"


def test_return_validates_clean_for_column_capable_fields():
    oqo = parse("works return id, open access, authorships")
    res = OQOValidator().validate(oqo)
    assert res.valid, res.errors


def test_filter_only_predicate_is_not_returnable():
    # has_doi is a filter predicate, not a result column — the parser passes it
    # through and the validator rejects it on the column capability.
    oqo = parse("works return has_doi")
    res = OQOValidator().validate(oqo)
    assert not res.valid
    assert any(e.type == "invalid_select_column" for e in res.errors)


# --------------------------------------------------------------------------- #
# Rendering
# --------------------------------------------------------------------------- #
def test_render_emits_return_last_and_friendly():
    oqo = parse("works where year >= 2020 return id, cited_by_count sort by year desc")
    out = render(oqo)
    assert out.endswith("return id, citation count")
    assert "sort by year desc" in out


def test_render_omits_return_when_select_empty():
    assert "return" not in render(parse("works where year >= 2020"))


def test_render_parse_round_trip():
    cases = [
        "works where year >= 2020 return id, title, cited by count",
        "works return open_access, authorships",
        "works where type is article sort by year desc return id, doi",
        "authors return id, display_name, works count",
        "sources return id, issn",
    ]
    for oql in cases:
        oqo = parse(oql)
        again = parse(render(oqo))
        assert again.to_dict() == oqo.to_dict(), oql


def test_return_word_in_search_value_round_trips():
    # `return` is now a reserved run-break word: MID-value it renders quoted
    # ("…") and folds back into the same single stemmed node. (A value whose
    # FIRST word is reserved is a pre-existing render/parse asymmetry shared by
    # all reserved words — `sample size matters` breaks identically on
    # pre-#450 master; tracked as a #363-class correctness gap, not covered
    # here.)
    from query_translation.oqo import LeafFilter
    oqo = OQO(get_rows="works",
              filter_rows=[LeafFilter(column_id="display_name.search",
                                      value="the return on investment",
                                      operator="contains")])
    out = render(oqo)
    assert '"return"' in out
    again = parse(out)
    assert again.to_dict() == oqo.to_dict()


def test_every_column_round_trips_on_every_entity():
    """Exhaustive: for EVERY entity and EVERY column-capable property, a
    one-column `return` renders to OQL that parses back to the same column.
    Locks the friendly-render map's round-trip-safety rule (a display_name is
    only used when it resolves back to the same column)."""
    checked = 0
    for entity in sorted(ENTITY_PROPERTIES):
        columns = get_entity_columns(entity)
        if not columns:
            continue
        try:
            parse(entity)
        except OQLError:
            # entity name has no OQL surface (e.g. `institution-types` — OQL
            # spells it `institution types`); entity-head naming is out of
            # scope for the return clause
            continue
        for col in sorted(columns):
            oqo = OQO(get_rows=entity, select=[col])
            out = render(oqo)
            again = parse(out)
            assert again.select == [col], (
                f"{entity}.{col}: rendered {out!r} parsed back as {again.select}"
            )
            checked += 1
    assert checked > 300  # sanity: the sweep actually covered the catalog
