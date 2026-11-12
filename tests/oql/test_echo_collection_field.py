"""A collection's echo keeps its field (oxjob #885, 2026-11-12).

`get works where corresponding institution is in the collection [UC campuses](col_uc)`
echoed `get works in the collection [UC campuses](col_uc)`, which reads back as any
UC affiliation: 960,638 works instead of 413,063, silently, in every shared link.
And `get works in the collection [X]` for a collection of sources or authors was a 400,
because today's grammar read it as the works themselves (`ids.openalex`).
"""
from unittest import mock

import pytest

from query_translation import oql_parser
from query_translation.oqo_canonicalizer import canonicalize_oqo
from query_translation.x_query import new_oql

TYPES = {"col_uc": "institutions", "col_pub": "publishers", "col_eu": "countries",
         "col_auth": "authors", "col_src": "sources", "col_w": "works"}


def _read(text):
    with mock.patch.object(oql_parser, "_collection_type", TYPES.get):
        return canonicalize_oqo(oql_parser.parse_either(text))


@pytest.mark.parametrize("text,column", [
    ("get works where corresponding institution is in the collection [UC](col_uc) and published in 2025",
     "corresponding_institution_ids"),
    ("get works where corresponding author is in the collection [Lab](col_auth) and published in 2025",
     "corresponding_author_ids"),
    ("get works where corresponding institution is not in the collection [UC](col_uc) and published in 2025",
     "corresponding_institution_ids"),
    ("get works where institution is in the collection [UC](col_uc) and published in 2025",
     "authorships.institutions.lineage"),
    ("get works where publisher is in the collection [P](col_pub) and published in 2025",
     "primary_location.source.host_organization_lineage"),
    ("get works where country is in the collection [EU](col_eu) and published in 2025",
     "authorships.countries"),
    ("get works where source is in the collection [S](col_src)", "primary_location.source.id"),
    ("get works where author is in the collection [Lab](col_auth)", "authorships.author.id"),
    ("get the count and percent open access of works where corresponding institution is in "
     "the collection [UC](col_uc) by year from 2015–2025", "corresponding_institution_ids"),
])
def test_the_echo_reads_back_to_the_same_query(text, column):
    oqo = _read(text)
    assert column in {getattr(f, "column_id", None) for f in oqo.filter_rows}
    echo = new_oql(oqo)
    assert _read(echo).to_dict() == oqo.to_dict(), echo


@pytest.mark.parametrize("text,column", [
    ("get works in the collection [S](col_src)", "primary_location.source.id"),
    ("get works in the collection [Lab](col_auth)", "authorships.author.id"),
    ("get works in the collection [EU](col_eu)", "authorships.countries"),
    ("get works in the collection [UC](col_uc)", "authorships.institutions.lineage"),
])
def test_a_bare_collection_of_other_things_means_their_works(text, column):
    leaf = next(f for f in _read(text).filter_rows if getattr(f, "operator", None) == "in collection")
    assert leaf.column_id == column


def test_a_bare_works_collection_is_still_the_works():
    leaf = next(f for f in _read("get works in the collection [W](col_w)").filter_rows
                if getattr(f, "operator", None) == "in collection")
    assert leaf.column_id == "ids.openalex"
