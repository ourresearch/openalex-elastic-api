"""works `mesh.*` filter/group_by plumbing (oxjob #1473). No ES, no app.

works-v35 maps `mesh` as an object array with the house keyword + `.lower`
subfields (works-v34 had it flattened and unindexed). Filters match any heading on
the work, case-insensitively, through `.lower`; group_by reads the keyword so bucket
keys keep NLM's capitalisation. The same code was run against a local ES 8.19 with
650 real works and matched ground truth (oxjob #1473 PLAN.md).

    PYTHONPATH=. venv/bin/python -m pytest tests/unit/test_mesh_filters.py --noconftest -q
"""

import pytest

from works.fields import fields

FIELDS = {f.param: f for f in fields}
MESH_PARAMS = [
    "mesh.descriptor_ui",
    "mesh.descriptor_name",
    "mesh.qualifier_ui",
    "mesh.qualifier_name",
]


def _query(param, value):
    f = FIELDS[param]
    f.value = value
    return f.build_query().to_dict()


@pytest.mark.parametrize("param", MESH_PARAMS)
def test_filters_read_the_lower_subfield(param):
    assert _query(param, "X") == {"term": {f"{param}.lower": "X"}}


@pytest.mark.parametrize("param", MESH_PARAMS)
def test_group_by_reads_the_keyword(param):
    # bucket keys keep PubMed's casing (Asthma, D001249), not the `.lower` copy
    assert FIELDS[param].es_sort_field() == param


def test_negation_and_null():
    assert _query("mesh.descriptor_ui", "!D001249") == {
        "bool": {"must_not": [{"term": {"mesh.descriptor_ui.lower": "D001249"}}]}
    }
    assert _query("mesh.descriptor_ui", "null") == {
        "bool": {"must_not": [{"exists": {"field": "mesh.descriptor_ui.lower"}}]}
    }
    assert _query("mesh.descriptor_ui", "!null") == {"exists": {"field": "mesh.descriptor_ui.lower"}}


def test_or_values_are_one_terms_clause():
    q = FIELDS["mesh.descriptor_ui"].build_terms_query(["D001249", "D001241"]).to_dict()
    assert q == {"terms": {"mesh.descriptor_ui.lower": ["D001249", "D001241"]}}


def test_major_topic_is_not_a_filter():
    # A flat mapping can't tie is_major_topic to one heading, so a filter on it would
    # mean "has any major heading", which nobody wants. It stays select-only.
    assert "mesh.is_major_topic" not in FIELDS


@pytest.mark.parametrize(
    "filter_string, oql",
    [
        ("mesh.descriptor_ui:D001249", "works where MeSH descriptor ID is D001249"),
        ('mesh.descriptor_name:"Pregnant Women"', 'works where MeSH descriptor is "Pregnant Women"'),
        (
            'mesh.descriptor_name:"Diabetes Mellitus, Type 2"',
            'works where MeSH descriptor is "Diabetes Mellitus, Type 2"',
        ),
        ("mesh.qualifier_ui:Q000188", "works where MeSH qualifier ID is Q000188"),
    ],
)
def test_oql_round_trip(filter_string, oql):
    from query_translation import oql_lang as L
    from query_translation.oql_renderer import render_oqo_to_oql
    from query_translation.url_parser import parse_url_to_oqo

    oqo = parse_url_to_oqo("works", filter_string=filter_string)
    rendered = render_oqo_to_oql(oqo)
    assert " ".join(rendered.split()).replace("(", "").replace(")", "") == oql
    assert L.parse(rendered).to_dict() == oqo.to_dict()


@pytest.mark.parametrize(
    "oql, url_filter",
    [
        # an unquoted space is AND and an unquoted comma starts the next filter on the
        # classic door, so a multi-word or comma value must come out quoted, whole
        ('works where MeSH descriptor is "Pregnant Women"', 'mesh.descriptor_name:"Pregnant Women"'),
        ('works where MeSH descriptor is not "Pregnant Women"', 'mesh.descriptor_name:"!Pregnant Women"'),
        (
            'works where MeSH descriptor is (Pregnancy or "Diabetes Mellitus, Type 2")',
            'mesh.descriptor_name:"Pregnancy|Diabetes Mellitus, Type 2"',
        ),
        ("works where MeSH descriptor is Asthma", "mesh.descriptor_name:Asthma"),
        # search columns keep their own quoting (quotes there mean a phrase)
        ("works where title has (machine learning)", "display_name.search:machine learning"),
    ],
)
def test_url_render_quotes_values_with_spaces_or_commas(oql, url_filter):
    from query_translation import oql_lang as L
    from query_translation.url_parser import parse_url_to_oqo
    from query_translation.url_renderer import render_oqo_to_url

    oqo = L.parse(oql)
    rendered = render_oqo_to_url(oqo)["filter"]
    assert rendered == url_filter
    assert parse_url_to_oqo("works", filter_string=rendered).to_dict() == oqo.to_dict()


@pytest.mark.parametrize("spelling", ['!"Pregnant Women"', '"!Pregnant Women"'])
def test_negated_quoted_value_both_spellings(spelling):
    # the GUI writes `!"a b"`; the renderer writes `"!a b"`. Both are NOT(one value).
    from elasticsearch_dsl import Search

    from core.filter import filter_records
    from query_translation.url_parser import parse_url_to_oqo

    s = filter_records(FIELDS, [{"mesh.descriptor_name": spelling}], Search())
    assert s.to_dict()["query"]["bool"]["filter"] == [
        {"bool": {"must_not": [{"term": {"mesh.descriptor_name.lower": "Pregnant Women"}}]}}
    ]
    leaf = parse_url_to_oqo("works", filter_string=f"mesh.descriptor_name:{spelling}").filter_rows[0]
    assert (leaf.value, leaf.is_negated) == ("Pregnant Women", True)


def test_oql_canonicalizes_id_case():
    from query_translation import oql_lang as L

    oqo = L.parse("works where MeSH descriptor ID is d001249")
    assert oqo.filter_rows[0].value == "D001249"
