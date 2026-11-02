"""oxjob #1300: the deprecated `sustainable_development_goals_aurora` works field is gone.

Aurora's SDG tags were frozen in October 2026 when the Jev-trained classifier took over
`sustainable_development_goals`, served as a deprecated column, and removed on 2 November 2026.
Docs written before then still carry it in ES `_source` until the next works rebuild (and in
Lakebase until each doc changes), so the schema must not serialize it, ES must not send it, and a
`select=` naming it must say it was removed and what to use instead.
"""

import pytest

from core.exceptions import APIQueryParamsError
from core.properties import ENTITY_PROPERTIES, get_selectable_fields

AURORA = "sustainable_development_goals_aurora"
ROWS = [{"id": "https://metadata.un.org/sdg/7", "display_name": "Affordable and clean energy", "score": 0.62}]


class _Req:
    def __init__(self, select):
        self.args = {"select": select}


def test_works_schema_drops_the_aurora_field_from_old_docs():
    from works.schemas import WorksSchema

    live = [{"id": "https://metadata.un.org/sdg/3", "display_name": "Good health and well-being", "score": 0.91}]
    out = WorksSchema(only=("sustainable_development_goals",)).dump(
        {"sustainable_development_goals": live, AURORA: ROWS}
    )
    assert out == {"sustainable_development_goals": live}
    assert AURORA not in WorksSchema().fields


def test_aurora_is_not_a_column_or_property():
    assert AURORA not in get_selectable_fields("works")
    assert not any(name == AURORA or name.startswith(AURORA + ".") for name in ENTITY_PROPERTIES["works"])


@pytest.mark.parametrize("helper", ["core.utils.process_only_fields", "ids.utils.process_id_only_fields"])
def test_select_of_the_removed_field_says_removed_and_names_the_replacement(helper):
    import importlib

    from works.schemas import WorksSchema

    mod, name = helper.rsplit(".", 1)
    fn = getattr(importlib.import_module(mod), name)
    with pytest.raises(APIQueryParamsError) as e:
        fn(_Req(f"id,sustainable_development_goals,{AURORA}"), WorksSchema)
    msg = str(e.value.args[0] if e.value.args else e.value)
    assert "was removed on 2 November 2026" in msg
    assert "Use sustainable_development_goals." in msg
    # other unknown fields keep the generic message
    with pytest.raises(APIQueryParamsError) as e2:
        fn(_Req("id,not_a_field"), WorksSchema)
    assert "is not a valid select field" in str(e2.value.args[0] if e2.value.args else e2.value)


def test_es_source_excludes_the_stale_field():
    from elasticsearch_dsl import Search

    from core.shared_view import set_source

    s = set_source("works-v40", Search())
    assert AURORA in s.to_dict()["_source"]["excludes"]


def test_x_sdgs_is_gone():
    assert "x_sdgs" not in get_selectable_fields("works")
    assert not any(name.startswith("x_sdgs") for name in ENTITY_PROPERTIES["works"])
    from query_translation import oql_lang

    src = open(oql_lang.__file__).read()
    assert "x_sdgs" not in src
