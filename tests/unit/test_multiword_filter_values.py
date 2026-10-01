"""Multi-word and comma values on non-search filters survive the classic URL door.

On the classic door an unquoted space is AND and an unquoted comma starts the next
filter, so `url_renderer` must quote such values (it used to drop the quotes:
`display_name:"Attention Is All You Need"` matched 4 works, its rendered
`x_query.url` matched 0). The GUI negates a quoted value as `!"a b"`, which
`filter_records` used to read as a literal quoted string (0 works instead of all
but 4). Found by #1473, fixed on master as a #1463 follow-up. No ES, no app.

    PYTHONPATH=. venv/bin/python -m pytest tests/unit/test_multiword_filter_values.py --noconftest -q
"""

import pytest
from elasticsearch_dsl import Search

from core.filter import filter_records
from query_translation.url_parser import parse_url_to_oqo
from query_translation.url_renderer import render_oqo_to_url
from works.fields import fields

FIELDS = {f.param: f for f in fields}
TITLE = "Attention Is All You Need"


@pytest.mark.parametrize(
    "filter_string",
    [
        f'display_name:"{TITLE}"',
        f'display_name:!"{TITLE}"',
        f'display_name:"{TITLE}|Deep Residual Learning for Image Recognition"',
        'display_name:"Diabetes Mellitus, Type 2"',
        f'display_name:"{TITLE}",type:article',
        "type:article|preprint",
        "display_name.search:machine learning",
    ],
)
def test_url_round_trip_keeps_the_query(filter_string):
    oqo = parse_url_to_oqo("works", filter_string=filter_string)
    rendered = render_oqo_to_url(oqo)["filter"]
    assert parse_url_to_oqo("works", filter_string=rendered).to_dict() == oqo.to_dict()


@pytest.mark.parametrize(
    "filter_string, rendered",
    [
        (f'display_name:"{TITLE}"', f'display_name:"{TITLE}"'),
        # bang outside the quotes: the spelling the GUI writes and its chip parser reads
        (f'display_name:"!{TITLE}"', f'display_name:!"{TITLE}"'),
        ('display_name:"Diabetes Mellitus, Type 2"', 'display_name:"Diabetes Mellitus, Type 2"'),
        ("type:article", "type:article"),
        ("type:article|preprint", "type:article|preprint"),
        # search columns keep their own quoting (quotes there mean a phrase)
        ("display_name.search:machine learning", "display_name.search:machine learning"),
    ],
)
def test_renderer_quotes_values_with_spaces_or_commas(filter_string, rendered):
    oqo = parse_url_to_oqo("works", filter_string=filter_string)
    assert render_oqo_to_url(oqo)["filter"] == rendered


@pytest.mark.parametrize("spelling", [f'!"{TITLE}"', f'"!{TITLE}"'])
def test_negated_quoted_value_both_spellings(spelling):
    s = filter_records(FIELDS, [{"display_name": spelling}], Search())
    assert s.to_dict()["query"]["bool"]["filter"] == [
        {"bool": {"must_not": [{"term": {"display_name.lower": TITLE}}]}}
    ]
    leaf = parse_url_to_oqo("works", filter_string=f"display_name:{spelling}").filter_rows[0]
    assert (leaf.value, leaf.is_negated) == (TITLE, True)
