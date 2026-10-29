"""Sync filters on every entity (oxjob #1917).

help.openalex.org (api/filtering, access/sync) promises from_created_date and from_updated_date on every entity
type. Awards had none (HTTP 400), and only works, authors and sources had the to_* bounds. Every list entity whose
index stores created_date / updated_date now carries all four, as inclusive ranges on those fields.
No ES needed: these assert on the queries the fields build.
"""
import copy
import importlib

import pytest

ENTITY_MODULES = [
    "authors", "awards", "concepts", "continents", "countries", "domains", "fields", "funders", "indexes",
    "institution_types", "institutions", "keywords", "languages", "licenses", "oa_statuses", "publishers", "sdgs",
    "source_lists", "source_types", "sources", "study_designs", "subfields", "topics", "work_types", "works",
]
EXPECTED = {
    "from_created_date": ("created_date", "gte"),
    "to_created_date": ("created_date", "lte"),
    "from_updated_date": ("updated_date", "gte"),
    "to_updated_date": ("updated_date", "lte"),
}


@pytest.mark.parametrize("module", ENTITY_MODULES)
@pytest.mark.parametrize("param", sorted(EXPECTED))
def test_sync_filter_builds_inclusive_range(module, param):
    fields_dict = importlib.import_module(f"{module}.fields").fields_dict
    assert param in fields_dict, f"{module} lacks {param}"
    f = copy.deepcopy(fields_dict[param])
    f.value = "2026-10-28"
    es_field, op = EXPECTED[param]
    assert f.build_query().to_dict() == {"range": {es_field: {op: "2026-10-28"}}}


@pytest.mark.parametrize("module", ENTITY_MODULES)
def test_sync_filter_rejects_a_non_date(module):
    from core.exceptions import APIQueryParamsError
    f = copy.deepcopy(importlib.import_module(f"{module}.fields").fields_dict["to_created_date"])
    f.value = "yesterday"
    with pytest.raises(APIQueryParamsError):
        f.build_query()
