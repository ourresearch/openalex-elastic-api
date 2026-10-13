"""get_index_name_by_id routes every OpenAlex id letter with its own index (oxjob #1617).

A letter with no branch returns None, and Search(index=None) searches every index on the cluster:
funder ids did that for each group-by display-name lookup (171 shards instead of 1).
"""

import pytest

import core.utils
from core.utils import get_index_name_by_id

# the settings core.utils routes with; a bare `import settings` can resolve to tests/settings.py when
# tests/functional and tests/unit run together
settings = core.utils.settings


@pytest.mark.parametrize(
    "openalex_id, setting",
    [
        ("https://openalex.org/F4320320300", "FUNDERS_INDEX"),
        ("F4320332161", "FUNDERS_INDEX"),
        ("https://openalex.org/G1234567", "AWARDS_INDEX"),
        ("C41008148", "CONCEPTS_INDEX"),
        ("I141945490", "INSTITUTIONS_INDEX"),
        ("P4310320990", "PUBLISHERS_INDEX"),
        ("S137773608", "SOURCES_INDEX"),
        ("T10017", "TOPICS_INDEX"),
        ("W2741809807", "WORKS_INDEX"),
    ],
)
def test_routes_each_id_letter_to_its_index(openalex_id, setting):
    assert get_index_name_by_id(openalex_id) == getattr(settings, setting)


def test_authors_follow_the_connection():
    assert get_index_name_by_id("A5023888391", "walden") == settings.AUTHORS_INDEX_WALDEN
    assert get_index_name_by_id("A5023888391") == settings.AUTHORS_INDEX_LEGACY
