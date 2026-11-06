"""Echo gaps fixed 2026-11-06 (oxjob #1555).

A thing's own place and flags read back as the thing's own columns. On production the echo of
`/institutions?filter=is_global_south:true` (`get institutions where it's from the global south`)
and of `/sources?filter=continent:europe` (`get sources in [Europe](Q46)`) were 400s when rerun:
the first read as the works column, the second as a country. `get publishers in [Brazil](BR)`
answered but echoed `where country_codes is BR`, which doesn't parse.

A count floor on a field split is its own `Only` sentence, like a thing split's
(`Only keywords with at least 50 works about kelp.`; it fell back to the general form).

`Show` takes any own field of the split's things, in the general form's words
(`Show h-index and last known institution.`); it knew only h-index and works count, so a
table of authors with their institution echoed `get authors who published works ...; then,
summarize each author using ...`.
"""
import pytest

import tests.oql._qt_loader  # noqa: F401
from core.properties import get_entity_properties
from query_translation import oql_lang as L
from query_translation.diagnostics import OQLError
from query_translation.oql_context import parse_context
from query_translation.oql_core import render_core
from query_translation.oql_parser import parse_either
from query_translation.oqo_canonicalizer import canonicalize_oqo
from query_translation.url_parser import parse_url_to_oqo


def _rows(text):
    return canonicalize_oqo(parse_either(text)).to_dict()["filter_rows"]


def _round_trip(oqo):
    oqo = canonicalize_oqo(oqo)
    text = render_core(oqo)
    assert text is not None
    assert canonicalize_oqo(parse_either(text)).to_dict() == oqo.to_dict(), text
    return text


# --- a thing's own flags and places --------------------------------------------------------

@pytest.mark.parametrize("entity,url,echo", [
    ("institutions", "is_global_south:true", "get institutions where it's from the global south"),
    ("institutions", "is_global_south:false", "get institutions where it's not from the global south"),
    ("sources", "is_global_south:true", "get sources where it's from the global south"),
    ("funders", "is_global_south:true", "get funders where it's from the global south"),
    ("sources", "continent:europe", "get sources in [Europe](Q46)"),
    ("funders", "continent:africa", "get funders in [Africa](Q15)"),
    ("publishers", "continent:europe", "get publishers in [Europe](Q46)"),
    ("institutions", "continent:europe", "get institutions in [Europe](Q46)"),
])
def test_a_things_own_flag_or_place_echoes_and_reads_back(entity, url, echo):
    assert _round_trip(parse_url_to_oqo(entity, filter_string=url)) == echo


def test_the_works_flag_stays_the_works_flag():
    assert _rows("get works where it's from the global south") == [
        {"column_id": "authorships.institutions.is_global_south", "value": True}]


@pytest.mark.parametrize("text,column", [
    ("get institutions where global south is true", "is_global_south"),
    ("get sources where global south is false", "is_global_south"),
    ("get locations where open access is true", "is_oa"),
])
def test_a_flag_word_on_a_thing_is_its_own_is_flag(text, column):
    assert _rows(text)[0]["column_id"] == column


def test_a_publishers_own_country_echoes_as_a_place():
    oqo = canonicalize_oqo(parse_either("get publishers in [Brazil](BR)"))
    assert oqo.to_dict()["filter_rows"] == [{"column_id": "country_codes", "value": "BR"}]
    assert _round_trip(oqo) == "get publishers in [Brazil](BR)"


def test_every_own_place_column_is_on_its_thing():
    for entity, country in L._THING_IN.items():
        props = get_entity_properties(entity)
        assert country in props and "continent" in props, entity


@pytest.mark.parametrize("entity", ["sources", "institutions"])
def test_a_list_of_continents_is_continents(entity):
    rows = _rows(f"get {entity} in ([Europe](Q46) or [Africa](Q15))")
    assert {r["column_id"] for r in rows[0]["filters"]} == {"continent"}
    assert {r["column_id"] for r in _rows(f"get {entity} in ([Brazil](BR) or [Chile](CL))")[0]["filters"]} \
        == {"country_code"}


# --- `Only` floors on field splits ---------------------------------------------------------

@pytest.mark.parametrize("text", [
    "get the count of works about kelp by keyword. Only keywords with at least 50 works about kelp.",
    "get the count and share of works about kelp by language. Only languages with more than 10 works about kelp.",
    "get the count of works about kelp by year and source type. "
    "Only source types with at least 100 works about kelp.",
    "get the count of works about kelp by SDG. Only SDGs with at least 5 works about kelp.",
    "get the count of works about kelp by domain. Only domains with at least 5 works about kelp.",
    "get the count of works about kelp by type. Only types with at least 5 works about kelp.",
    "get the count of works about kelp by continent. Only continents with at least 5 works about kelp.",
    "get the count of works about kelp by license. Only licenses with at least 5 works about kelp.",
    "get the count of works about kelp by institution type. "
    "Only institution types with at least 5 works about kelp.",
    "get the count of works about kelp by open access status. "
    "Only open access statuses with at least 5 works about kelp.",
    # a year split carries the years; the floor's works say them too, in the works' own order
    "get the count of works about kelp by year since 2015. Only years with at least 500 works since 2015 about kelp.",
    "get the count of works about kelp by year since 2015 and keyword. "
    "Only keywords with at least 10 works since 2015 about kelp.",
    "get the count of works about kelp by year since 2015 and institution. "
    "Only institutions with at least 10 works since 2015 about kelp.",
])
def test_a_field_split_takes_a_count_floor(text):
    oqo = canonicalize_oqo(parse_either(text))
    assert any(g.where is not None for g in oqo.group_by)
    assert render_core(oqo) == text


def test_the_general_forms_floor_echoes_as_a_sentence():
    oqo = canonicalize_oqo(parse_either(
        "get works where title-abstract-keywords has (kelp); then group those works by keyword "
        "where count of those works >= (50); finally, summarize using count"))
    assert render_core(oqo) == ("get the count of works about kelp by keyword. "
                                "Only keywords with at least 50 works about kelp.")


def _suggest(text):
    pos = text.index("|")
    return [s["value"] for s in parse_context(text.replace("|", ""), pos)["context"]["suggestions"]]


def test_the_editor_offers_the_splits_own_plural_after_only():
    assert "Only" in _suggest("get the count of works about kelp by keyword. |")
    assert _suggest("get the count of works about kelp by keyword. Only |") == ["keywords"]
    assert _suggest("get the count of works about kelp by year and institution. Only |") == \
        ["institutions", "years"]
    assert "with at least" in _suggest(
        "get the count of works about kelp by corresponding author. Only corresponding authors |")


# --- `Show` any own field of the split's things --------------------------------------------

@pytest.mark.parametrize("general,sentence", [
    ("get works where title-abstract has kelp and year >= 2020; then, group those works by author; "
     "finally, summarize using count, h-index, and last known institution",
     "get the count of works since 2020 with kelp in the title or abstract by author. "
     "Show h-index and last known institution."),
    ("get works where title-abstract has kelp; then, group those works by author; finally, summarize using count and ORCID",
     "get the count of works with kelp in the title or abstract by author. Show ORCID."),
    ("get works where title-abstract has kelp; then, group those works by institution; "
     "finally, summarize using count, country, and type",
     "get the count of works with kelp in the title or abstract by institution. Show country and type."),
])
def test_own_fields_beside_groups_echo_as_show(general, sentence):
    oqo = canonicalize_oqo(parse_either(general))
    assert render_core(oqo) == sentence
    assert canonicalize_oqo(parse_either(sentence)).to_dict() == oqo.to_dict()


@pytest.mark.parametrize("text", [
    "get the count of works about kelp by author. Show citation count.",
    "get the count of works about kelp by author. Show i10-index.",
    "get the count of works about kelp by author, highest h-index first. Show last known institution.",
])
def test_show_reads_back(text):
    assert render_core(canonicalize_oqo(parse_either(text))) == text


def test_show_needs_a_split_by_things_that_have_the_field():
    with pytest.raises(OQLError):
        parse_either("get the count of works about kelp by year. Show last known institution.")
