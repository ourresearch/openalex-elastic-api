"""oxjob #1300: the deprecated `sustainable_development_goals_aurora` works field.

Aurora's SDG tags, frozen in October 2026 when the Jev-trained classifier took over
`sustainable_development_goals`; removed in November 2026. Output only: it must
serialize from the ES/Lakebase `_source` (WorksSchema is what picks fields to dump;
`set_source` only excludes abstract/embeddings/fulltext) and be select-able, but have
no filter, group_by or OQL surface. The `x_sdgs` shadow field is gone everywhere.
"""

from core.properties import ENTITY_PROPERTIES, get_selectable_fields

AURORA = "sustainable_development_goals_aurora"
ROWS = [{"id": "https://metadata.un.org/sdg/7", "display_name": "Affordable and clean energy", "score": 0.62}]


def test_works_schema_dumps_the_deprecated_aurora_field():
    from works.schemas import WorksSchema

    assert WorksSchema(only=(AURORA,)).dump({AURORA: ROWS}) == {AURORA: ROWS}
    # a work Aurora never tagged (or a doc written before the field existed)
    assert WorksSchema(only=(AURORA,)).dump({}) == {AURORA: []}


def test_both_sdg_fields_dump_side_by_side_and_x_sdgs_is_not_a_schema_field():
    from works.schemas import WorksSchema

    other = [{"id": "https://metadata.un.org/sdg/3", "display_name": "Good health and well-being", "score": 0.91}]
    out = WorksSchema(only=("sustainable_development_goals", AURORA)).dump(
        {"sustainable_development_goals": other, AURORA: ROWS, "x_sdgs": ROWS}
    )
    assert out == {"sustainable_development_goals": other, AURORA: ROWS}
    assert "x_sdgs" not in WorksSchema().fields
    # output order: the deprecated field sits right after the live one
    names = list(WorksSchema().fields)
    assert names.index(AURORA) == names.index("sustainable_development_goals") + 1


def test_aurora_field_is_column_only():
    assert AURORA in get_selectable_fields("works")
    works = ENTITY_PROPERTIES["works"]
    assert not any(name == AURORA or name.startswith(AURORA + ".") for name in works)


def test_x_sdgs_is_gone():
    assert "x_sdgs" not in get_selectable_fields("works")
    assert not any(name.startswith("x_sdgs") for name in ENTITY_PROPERTIES["works"])
    from query_translation import oql_lang

    src = open(oql_lang.__file__).read()
    assert "x_sdgs" not in src
