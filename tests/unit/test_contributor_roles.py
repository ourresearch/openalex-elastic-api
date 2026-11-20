"""Per-authorship `contributor_roles` on works (oxjob #2075). No ES, no app.

Each authorship carries the CRediT roles its author played, as a list of {id, display_name} ([] when none), read from
`authorships_full` for a single work. There is deliberately no works filter, group_by or sort on
`authorships.contributor_roles.id` on its own: the filter that ships pairs an author with a role on the same
authorship (oxjob #2075, D11).

    PYTHONPATH=. venv/bin/python -m pytest tests/unit/test_contributor_roles.py --noconftest -q
"""

import pytest

from works.fields import fields_dict as works_fields

PARAM = "authorships.contributor_roles.id"
FULL = "https://openalex.org/contributor-roles/software"


def test_no_standalone_role_filter_on_works():
    assert PARAM not in works_fields


def test_authorship_dumps_contributor_roles_after_is_corresponding():
    from works.schemas import WorksSchema

    rows = [{"id": FULL, "display_name": "Software"}]
    out = WorksSchema(only=("authorships",)).dump(
        {"authorships": [{"is_corresponding": True, "contributor_roles": rows, "raw_author_name": "A"}]})
    authorship = out["authorships"][0]
    assert authorship["contributor_roles"] == rows
    keys = list(authorship)
    assert keys[keys.index("is_corresponding") + 1] == "contributor_roles"
    assert list(authorship["contributor_roles"][0]) == ["id", "display_name"]


@pytest.mark.parametrize("authorship", [{"is_corresponding": False}, {"contributor_roles": None}])
def test_authorship_without_roles_dumps_an_empty_list(authorship):
    # absent in the doc (no role tagged, or before the works re-sync reaches it), or null -> []
    from works.schemas import WorksSchema

    out = WorksSchema(only=("authorships",)).dump({"authorships": [authorship]})
    assert out["authorships"][0]["contributor_roles"] == []


def test_single_work_dumps_contributor_roles_from_authorships_full():
    from elasticsearch_dsl import AttrDict
    from works.schemas import WorksSchema

    rows = [{"id": FULL, "display_name": "Software"}]
    doc = AttrDict({
        "authorships": [{"raw_author_name": "A"}],
        "authorships_full": [{"raw_author_name": "A", "contributor_roles": rows}],
    })
    schema = WorksSchema(only=("authorships",), context={"single_record": True})
    assert schema.dump(doc)["authorships"][0]["contributor_roles"] == rows
