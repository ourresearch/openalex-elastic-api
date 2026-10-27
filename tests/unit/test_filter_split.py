"""A comma inside a search filter's value is text (oxjob #1883).

12% of titles hold a comma, and `filter=title.search:<title>` split at it and answered
400. The edge error advised %2C, which can't work: clients that encode the whole value
send every separator as %2C too, so the API sees the same decoded string. Now a comma
inside a search filter's value separates filters only when a filter key and its colon
follow it directly.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from core.filter_split import split_filter_string


@pytest.mark.parametrize("raw, parts", [
    # unchanged: plain multi-filter, quoted commas, non-search values
    ("type:article,publication_year:2020", ["type:article", "publication_year:2020"]),
    ('type:article,raw_affiliation_strings.search:"Dept of Chemistry, UCLA"',
     ["type:article", 'raw_affiliation_strings.search:"Dept of Chemistry, UCLA"']),
    ("type:article,book", ["type:article", "book"]),  # still a colonless (400) segment
    ("doi:10.1/a,b", ["doi:10.1/a", "b"]),
    ("title.search:cancer,type:article", ["title.search:cancer", "type:article"]),
    ("title.search:cancer,publication-year:2020", ["title.search:cancer", "publication-year:2020"]),
    # new: a comma inside a search value
    ("title.search:Music and British Culture, 1785",
     ["title.search:Music and British Culture, 1785"]),
    ("title.search:Music and British Culture, 1785,type:book",
     ["title.search:Music and British Culture, 1785", "type:book"]),
    ("title.search:Software survey: VOSviewer, a computer program for bibliometric mapping",
     ["title.search:Software survey: VOSviewer, a computer program for bibliometric mapping"]),
    ("abstract.search:3,4-methylenedioxymethamphetamine treatment",
     ["abstract.search:3,4-methylenedioxymethamphetamine treatment"]),
    ("type:article,title.search:Hello Brand, let's take a selfie,is_oa:true",
     ["type:article", "title.search:Hello Brand, let's take a selfie", "is_oa:true"]),
    ("title_and_abstract.search:dogs,cats", ["title_and_abstract.search:dogs,cats"]),
])
def test_split(raw, parts):
    assert split_filter_string(raw) == parts


def test_filter_door_and_oqo_echo_split_alike():
    from core.utils import map_filter_params
    from query_translation.url_parser import split_filter_string as oqo_split

    raw = "title.search:Music and British Culture, 1785,type:book"
    assert oqo_split is split_filter_string
    assert map_filter_params(raw) == [
        {"title.search": "Music and British Culture, 1785"},
        {"type": "book"},
    ]


def test_colonless_non_search_value_still_400s():
    from core.exceptions import APIQueryParamsError
    from core.utils import map_filter_params

    with pytest.raises(APIQueryParamsError):
        map_filter_params("type:article,book")


@pytest.mark.parametrize("value, echoed", [
    ("Music and British Culture, 1785", "Music and British Culture 1785"),
    ("3,4-methylenedioxymethamphetamine treatment", '"3,4-methylenedioxymethamphetamine" treatment'),
    ("costs of 1,000, patients", 'costs of "1,000" patients'),
    ('"Dept of Chemistry, UCLA" cancer', '"Dept of Chemistry, UCLA" cancer'),
])
def test_echo_keeps_digit_commas(value, echoed):
    from query_translation.url_parser import _search_value_commas

    assert _search_value_commas(value) == echoed

