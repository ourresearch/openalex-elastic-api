"""OQL reads and echoes `is_traditional` (oxjob #2064): `traditional scholarly work is true|false`, the alias
`traditional`, and the flag sentence "it's (not) a traditional scholarly work"."""
import pytest

from query_translation.oql_lang import parse
from query_translation.oql_pipeline import render_pipeline_line
from query_translation.oqo_canonicalizer import canonicalize_oqo

TRUE = [{"column_id": "is_traditional", "value": True}]
FALSE = [{"column_id": "is_traditional", "value": False}]


def _rows(q):
    return canonicalize_oqo(parse(q)).to_dict()["filter_rows"]


@pytest.mark.parametrize("q, rows", [
    ("get works where traditional scholarly work is true", TRUE),
    ("get works where traditional is true", TRUE),
    ("get works where it's a traditional scholarly work", TRUE),
    ("get works where traditional scholarly work is false", FALSE),
    ("get works where it's not a traditional scholarly work", FALSE),
    ("get works where it isn't a traditional scholarly work", FALSE),
])
def test_reads(q, rows):
    assert _rows(q) == rows


def test_echoes_as_its_sentence():
    o = canonicalize_oqo(parse("get works where traditional scholarly work is false and type is article"))
    echo = render_pipeline_line(o)
    assert echo == "get works where it's not a traditional scholarly work and type is [article](article)"
    assert canonicalize_oqo(parse(echo)).to_dict() == o.to_dict()


def test_groups_by_it():
    o = canonicalize_oqo(parse("get works where year is 2020; then group by traditional scholarly work"))
    assert o.to_dict()["group_by"] == [{"column_id": "is_traditional"}]
