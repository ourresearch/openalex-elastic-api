"""OQL words for the query-time join filters (oxjob #1526).

    PYTHONPATH=. venv/bin/python -m pytest tests/oql/test_join_filters_oql.py --noconftest -q
"""

import pytest

from query_translation import oql_lang as L
from query_translation.validator import validate_oqo


@pytest.mark.parametrize(
    "oql, column",
    [
        ("works where source country is (CA)", "primary_location.source.country_code"),
        ("works where source global south is true", "primary_location.source.is_global_south"),
        ("works where source OJS is true", "primary_location.source.is_ojs"),
        ("works where source high OA rate is true", "primary_location.source.is_high_oa_rate"),
        ("works where source preprint repository is true", "primary_location.source.is_preprint_repository"),
        ("works where source h-index > (50)", "primary_location.source.summary_stats.h_index"),
        ("works where source 2-year mean citedness > (5)", "primary_location.source.summary_stats.2yr_mean_citedness"),
        ("works where publisher country is (BR)", "primary_location.source.host_organization.country_code"),
        ("works where funder country is (CA)", "funders.country_code"),
        ("works where institution region is (Catalonia)", "authorships.institutions.geo.region"),
        ("works where institution city is (Paris)", "authorships.institutions.geo.city"),
        ("sources where publisher country is (BR)", "host_organization.country_code"),
        ("authors where institution region is (Catalonia)", "last_known_institutions.geo.region"),
        ("authors where institution city is (Paris)", "last_known_institutions.geo.city"),
        ("awards where funder country is (CA)", "funder.country_code"),
    ],
)
def test_word_parses_to_the_join_column_and_validates(oql, column):
    oqo = L.parse(oql)
    assert oqo.to_dict()["filter_rows"][0]["column_id"] == column
    assert validate_oqo(oqo).valid, validate_oqo(oqo).to_dict()


@pytest.mark.parametrize(
    "oql",
    [
        "works where institution region is (Catalonia)",
        "works where source h-index > (50)",
        "authors where institution city is (Paris)",
        "works where source OJS is (true)",
    ],
)
def test_renders_back_identically(oql):
    assert L.render(L.parse(oql)) == oql


def test_group_by_a_join_column_is_invalid():
    oqo = L.parse("works where year is (2024) group by source country")
    assert not validate_oqo(oqo).valid
