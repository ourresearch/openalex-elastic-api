import pytest

from core.exceptions import APIQueryParamsError
from core.utils import (
    is_wrapped_in_unescaped_quotes,
    map_filter_params,
    map_sort_params,
    split_filter_string,
    strip_outer_quotes_and_unescape,
)


class TestFilterParamMapping:
    def test_basic_filter_mapping(self, client):
        filter_params = "publication_year:2020,display_name.search:covid-19 deaths,cited_by_count:>200"
        parsed_params = map_filter_params(filter_params)
        assert parsed_params == [
            {"publication_year": "2020"},
            {"display_name.search": "covid-19 deaths"},
            {"cited_by_count": ">200"},
        ]

    def test_filter_mapping_with_url(self, client):
        filter_params = "publication_year:2020,display_name.search:covid-19 deaths,author.id:https://openalex.org/C234343"
        parsed_params = map_filter_params(filter_params)
        assert parsed_params == [
            {"publication_year": "2020"},
            {"display_name.search": "covid-19 deaths"},
            {"author.id": "https://openalex.org/C234343"},
        ]

    def test_filter_mapping_with_hyphens(self, client):
        filter_params = "publication-year:2020,display-name.search:covid-19 deaths,author.id:https://openalex.org/C234343,cited-by_count:>200"
        parsed_params = map_filter_params(filter_params)
        assert parsed_params == [
            {"publication_year": "2020"},
            {"display_name.search": "covid-19 deaths"},
            {"author.id": "https://openalex.org/C234343"},
            {"cited_by_count": ">200"},
        ]

    def test_filter_mapping_with_search_quotes(self, client):
        filter_params = 'publication-year:2020,title.search:"covid-19 deaths"'
        parsed_params = map_filter_params(filter_params)
        assert parsed_params == [
            {"publication_year": "2020"},
            {"title.search": '"covid-19 deaths"'},
        ]

    def test_filter_mapping_with_commas_inside_quotes(self, client):
        """Test that commas inside quoted strings are preserved, not split."""
        filter_params = 'type:article,raw_affiliation_strings.search:"Department of Chemistry, University of California, Berkeley"'
        parsed_params = map_filter_params(filter_params)
        assert parsed_params == [
            {"type": "article"},
            {"raw_affiliation_strings.search": '"Department of Chemistry, University of California, Berkeley"'},
        ]

    def test_filter_mapping_with_multiple_quoted_values(self, client):
        """Test multiple filters with commas inside quotes."""
        filter_params = 'title.search:"Machine Learning, Deep Learning",raw_affiliation_strings.search:"Dept of CS, MIT, Cambridge, MA"'
        parsed_params = map_filter_params(filter_params)
        assert parsed_params == [
            {"title.search": '"Machine Learning, Deep Learning"'},
            {"raw_affiliation_strings.search": '"Dept of CS, MIT, Cambridge, MA"'},
        ]

    def test_filter_mapping_with_multiple_colons(self, client):
        filter_params = "publication-year:2020,title.search:book 1: how to win friends"
        parsed_params = map_filter_params(filter_params)
        assert parsed_params == [
            {"publication_year": "2020"},
            {"title.search": "book 1: how to win friends"},
        ]

    def test_filter_mapping_with_same_keys(self, client):
        filter_params = "publication-year:2020,publication_year:2021,title.search:book 1: how to win friends"
        parsed_params = map_filter_params(filter_params)
        assert parsed_params == [
            {"publication_year": "2020"},
            {"publication_year": "2021"},
            {"title.search": "book 1: how to win friends"},
        ]

    def test_filter_mapping_rejects_empty_value(self, client):
        with pytest.raises(APIQueryParamsError) as exc_info:
            map_filter_params("doi:")
        assert "Invalid filter value for 'doi'" in str(exc_info.value)
        assert "cannot be empty" in str(exc_info.value)

    def test_filter_mapping_rejects_none_value(self, client):
        with pytest.raises(APIQueryParamsError) as exc_info:
            map_filter_params("doi:None")
        assert "Invalid filter value for 'doi'" in str(exc_info.value)

    def test_filter_mapping_allows_null_value(self, client):
        """null is a valid filter value meaning 'field does not exist'."""
        result = map_filter_params("doi:null")
        assert result == [{"doi": "null"}]

    def test_filter_mapping_rejects_undefined_value(self, client):
        with pytest.raises(APIQueryParamsError) as exc_info:
            map_filter_params("doi:undefined")
        assert "Invalid filter value for 'doi'" in str(exc_info.value)

    def test_filter_mapping_rejects_empty_in_middle(self, client):
        with pytest.raises(APIQueryParamsError) as exc_info:
            map_filter_params("publication_year:2020,doi:,cited_by_count:>10")
        assert "Invalid filter value for 'doi'" in str(exc_info.value)


class TestQuoteHelpers:
    """Direct coverage for the quote-aware helpers used by filter parsing."""

    @pytest.mark.parametrize(
        "value, expected",
        [
            ('"abc"', True),
            ('"a \\"b\\" c"', True),   # escaped inner quotes, real outer
            ('"a\\""', True),           # `\"` is inner escape, trailing `"` closes
            ('"a\\"', False),           # final `"` is escaped -> unbalanced
            ('"abc', False),            # unbalanced
            ('abc"', False),            # unbalanced
            ('""', True),               # empty quoted value
            ('"\\\\"', True),           # quoted single backslash
        ],
    )
    def test_is_wrapped_in_unescaped_quotes(self, value, expected):
        assert is_wrapped_in_unescaped_quotes(value) is expected

    @pytest.mark.parametrize(
        "value, expected",
        [
            ('"abc"', "abc"),
            ('"a \\"b\\" c"', 'a "b" c'),
            ('"a\\\\b"', "a\\b"),       # `\\` -> `\`
            ('"a\\nb"', "a\\nb"),      # other backslash escapes are left alone
            ('""', ""),
        ],
    )
    def test_strip_outer_quotes_and_unescape(self, value, expected):
        assert strip_outer_quotes_and_unescape(value) == expected

    def test_split_filter_string_keeps_escaped_quote_inside_quoted(self):
        # `\"` inside the quoted region must not close the quote; the
        # comma that follows is therefore part of the value.
        parts = split_filter_string(
            'raw_affiliation_strings:"a \\"b, c\\" d",type:article'
        )
        assert parts == [
            'raw_affiliation_strings:"a \\"b, c\\" d"',
            "type:article",
        ]

    def test_split_filter_string_plain_comma_in_quotes(self):
        parts = split_filter_string(
            'type:article,raw_affiliation_strings.search:"Dept, UCLA"'
        )
        assert parts == [
            "type:article",
            'raw_affiliation_strings.search:"Dept, UCLA"',
        ]


class TestSortParamMapping:
    def test_sort_mapping_basic(self, client):
        sort_params = "publication_year:desc,cited_by_count"
        parsed_params = map_sort_params(sort_params)
        assert parsed_params == {"publication_year": "desc", "cited_by_count": "asc"}

    def test_sort_mapping_hyphen(self, client):
        sort_params = "publication-year:desc,cited-by-count"
        parsed_params = map_sort_params(sort_params)
        assert parsed_params == {"publication_year": "desc", "cited_by_count": "asc"}
