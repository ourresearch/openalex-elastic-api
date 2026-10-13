"""get_index_name_by_id routes every OpenAlex id letter with its own index (oxjob #1617).

A letter with no branch returns None, and Search(index=None) searches every index on the cluster:
funder ids did that for each group-by display-name lookup (171 shards instead of 1).
"""

import pytest

import settings
from core.utils import get_index_name_by_id


@pytest.mark.parametrize(
    "openalex_id, index",
    [
        ("https://openalex.org/F4320320300", settings.FUNDERS_INDEX),
        ("F4320332161", settings.FUNDERS_INDEX),
        ("https://openalex.org/G1234567", settings.AWARDS_INDEX),
        ("C41008148", settings.CONCEPTS_INDEX),
        ("I141945490", settings.INSTITUTIONS_INDEX),
        ("P4310320990", settings.PUBLISHERS_INDEX),
        ("S137773608", settings.SOURCES_INDEX),
        ("T10017", settings.TOPICS_INDEX),
        ("W2741809807", settings.WORKS_INDEX),
    ],
)
def test_routes_each_id_letter_to_its_index(openalex_id, index):
    assert get_index_name_by_id(openalex_id) == index


def test_authors_follow_the_connection():
    assert get_index_name_by_id("A5023888391", "walden") == settings.AUTHORS_INDEX_WALDEN
    assert get_index_name_by_id("A5023888391") == settings.AUTHORS_INDEX_LEGACY
