"""
Tests for OQL rendering and parsing.

Tests both the human-readable and technical formats, and round-trip conversions.
"""

import pytest
from query_translation.oqo import OQO, LeafFilter, BranchFilter
from query_translation.oql_renderer import render_oqo_to_oql, OQLRenderer
from query_translation.oql_parser import parse_oql_to_oqo, OQLParser, OQLParseError


class TestOQLRenderer:
    """Tests for OQO -> OQL rendering."""
    
    def test_simple_entity_type(self):
        """Test rendering entity type."""
        oqo = OQO(get_rows="works")
        result = render_oqo_to_oql(oqo)
        assert result == "Works"
    
    def test_entity_type_with_hyphen(self):
        """Test entity types with hyphens."""
        oqo = OQO(get_rows="source-types")
        result = render_oqo_to_oql(oqo)
        assert result == "Source Types"
    
    def test_boolean_filter_true(self):
        """Test boolean filter with true value renders as 'it's X'."""
        oqo = OQO(
            get_rows="works",
            filter_rows=[
                LeafFilter(column_id="open_access.is_oa", value=True)
            ]
        )
        result = render_oqo_to_oql(oqo)
        assert result == "Works where it's Open Access"
    
    def test_boolean_filter_false(self):
        """Test boolean filter with false value renders as 'it's not X'."""
        oqo = OQO(
            get_rows="works",
            filter_rows=[
                LeafFilter(column_id="open_access.is_oa", value=False)
            ]
        )
        result = render_oqo_to_oql(oqo)
        assert result == "Works where it's not Open Access"
    
    def test_boolean_filter_global_south(self):
        """Test Global South boolean filter."""
        oqo = OQO(
            get_rows="works",
            filter_rows=[
                LeafFilter(column_id="institutions.is_global_south", value=True)
            ]
        )
        result = render_oqo_to_oql(oqo)
        assert result == "Works where it's from Global South"
    
    def test_entity_value_with_display_name(self):
        """Test entity values include display name before bracketed ID."""
        oqo = OQO(
            get_rows="works",
            filter_rows=[
                LeafFilter(column_id="authorships.countries", value="countries/ca")
            ]
        )
        result = render_oqo_to_oql(oqo)
        assert result == "Works where Country is Canada [countries/ca]"
    
    def test_entity_value_sdg(self):
        """Test SDG entity value with display name."""
        oqo = OQO(
            get_rows="works",
            filter_rows=[
                LeafFilter(column_id="sustainable_development_goals.id", value="sdgs/2")
            ]
        )
        result = render_oqo_to_oql(oqo)
        assert result == "Works where Sustainable Development Goals is Zero Hunger [sdgs/2]"
    
    def test_entity_value_type(self):
        """Test work type entity value."""
        oqo = OQO(
            get_rows="works",
            filter_rows=[
                LeafFilter(column_id="type", value="types/article")
            ]
        )
        result = render_oqo_to_oql(oqo)
        assert result == "Works where type is Article [types/article]"
    
    def test_comparison_filter(self):
        """Test comparison filters use display names."""
        oqo = OQO(
            get_rows="works",
            filter_rows=[
                LeafFilter(column_id="publication_year", value=2020, operator=">=")
            ]
        )
        result = render_oqo_to_oql(oqo)
        assert result == "Works where year >= 2020"
    
    def test_search_filter(self):
        """Test search filters use display names."""
        oqo = OQO(
            get_rows="works",
            filter_rows=[
                LeafFilter(column_id="title_and_abstract.search", value="machine learning", operator="contains")
            ]
        )
        result = render_oqo_to_oql(oqo)
        assert result == 'Works where title & abstract contains "machine learning"'
    
    def test_null_value(self):
        """Test null values render as 'unknown'."""
        oqo = OQO(
            get_rows="works",
            filter_rows=[
                LeafFilter(column_id="language", value=None)
            ]
        )
        result = render_oqo_to_oql(oqo)
        assert result == "Works where language is unknown"
    
    def test_multiple_filters(self):
        """Test multiple filters joined by 'and'."""
        oqo = OQO(
            get_rows="works",
            filter_rows=[
                LeafFilter(column_id="open_access.is_oa", value=True),
                LeafFilter(column_id="publication_year", value=2020, operator=">="),
                LeafFilter(column_id="authorships.countries", value="countries/ca")
            ]
        )
        result = render_oqo_to_oql(oqo)
        assert "it's Open Access" in result
        assert "year >= 2020" in result
        assert "Canada [countries/ca]" in result
        assert " and " in result
    
    def test_or_branch_filter(self):
        """Test OR branch filters with parentheses."""
        oqo = OQO(
            get_rows="works",
            filter_rows=[
                BranchFilter(
                    join="or",
                    filters=[
                        LeafFilter(column_id="type", value="types/article"),
                        LeafFilter(column_id="type", value="types/book")
                    ]
                )
            ]
        )
        result = render_oqo_to_oql(oqo)
        assert result.startswith("Works where (")
        assert "Article [types/article]" in result
        assert "Book [types/book]" in result
        assert " or " in result
    
    def test_sort_with_display_name(self):
        """Test sort uses display name."""
        oqo = OQO(
            get_rows="works",
            filter_rows=[
                LeafFilter(column_id="open_access.is_oa", value=True)
            ],
            sort_by_column="cited_by_count",
            sort_by_order="desc"
        )
        result = render_oqo_to_oql(oqo)
        assert "; sort by citations desc" in result
    
    def test_sample(self):
        """Test sample clause."""
        oqo = OQO(
            get_rows="works",
            filter_rows=[
                LeafFilter(column_id="publication_year", value=2024, operator=">=")
            ],
            sample=100
        )
        result = render_oqo_to_oql(oqo)
        assert "; sample 100" in result
    
    def test_negation(self):
        """Test negation operator."""
        oqo = OQO(
            get_rows="works",
            filter_rows=[
                LeafFilter(column_id="type", value="types/article", operator="is not")
            ]
        )
        result = render_oqo_to_oql(oqo)
        assert "is not Article [types/article]" in result
    
    def test_complex_query(self):
        """Test the example from the user's request."""
        oqo = OQO(
            get_rows="works",
            filter_rows=[
                LeafFilter(column_id="open_access.is_oa", value=True),
                LeafFilter(column_id="sustainable_development_goals.id", value="sdgs/2"),
                LeafFilter(column_id="authorships.countries", value="countries/ca"),
                LeafFilter(column_id="institutions.is_global_south", value=True),
                LeafFilter(column_id="publication_year", value=2020, operator=">=")
            ]
        )
        result = render_oqo_to_oql(oqo)
        
        assert "it's Open Access" in result
        assert "Zero Hunger [sdgs/2]" in result
        assert "Canada [countries/ca]" in result
        assert "it's from Global South" in result
        assert "year >= 2020" in result


class TestOQLParser:
    """Tests for OQL -> OQO parsing."""
    
    def test_parse_simple_entity(self):
        """Test parsing simple entity type."""
        oql = "Works"
        oqo = parse_oql_to_oqo(oql)
        assert oqo.get_rows == "works"
        assert oqo.filter_rows == []
    
    def test_parse_boolean_its_pattern(self):
        """Test parsing 'it's X' boolean pattern."""
        oql = "Works where it's Open Access"
        oqo = parse_oql_to_oqo(oql)
        
        assert oqo.get_rows == "works"
        assert len(oqo.filter_rows) == 1
        f = oqo.filter_rows[0]
        assert isinstance(f, LeafFilter)
        assert f.column_id == "open_access.is_oa"
        assert f.value is True
    
    def test_parse_boolean_its_not_pattern(self):
        """Test parsing 'it's not X' boolean pattern."""
        oql = "Works where it's not Open Access"
        oqo = parse_oql_to_oqo(oql)
        
        f = oqo.filter_rows[0]
        assert f.column_id == "open_access.is_oa"
        assert f.value is False
    
    def test_parse_boolean_global_south(self):
        """Test parsing Global South boolean."""
        oql = "Works where it's from Global South"
        oqo = parse_oql_to_oqo(oql)
        
        f = oqo.filter_rows[0]
        assert f.column_id == "institutions.is_global_south"
        assert f.value is True
    
    def test_parse_bracketed_id_only(self):
        """Test parsing bracketed ID without display name."""
        oql = "Works where Country is [countries/ca]"
        oqo = parse_oql_to_oqo(oql)
        
        f = oqo.filter_rows[0]
        assert f.column_id == "authorships.countries"
        assert f.value == "countries/ca"
    
    def test_parse_bracketed_id_with_display_name(self):
        """Test parsing bracketed ID with display name."""
        oql = "Works where Country is Canada [countries/ca]"
        oqo = parse_oql_to_oqo(oql)
        
        f = oqo.filter_rows[0]
        assert f.column_id == "authorships.countries"
        assert f.value == "countries/ca"  # ID is the source of truth
    
    def test_parse_sdg_with_display_name(self):
        """Test parsing SDG with display name."""
        oql = "Works where Sustainable Development Goals is Zero Hunger [sdgs/2]"
        oqo = parse_oql_to_oqo(oql)
        
        f = oqo.filter_rows[0]
        assert f.column_id == "sustainable_development_goals.id"
        assert f.value == "sdgs/2"
    
    def test_parse_comparison_display_name(self):
        """Test parsing comparison with display name."""
        oql = "Works where year >= 2020"
        oqo = parse_oql_to_oqo(oql)
        
        f = oqo.filter_rows[0]
        assert f.column_id == "publication_year"
        assert f.value == 2020
        assert f.operator == ">="
    
    def test_parse_comparison_technical_name(self):
        """Test parsing comparison with technical name."""
        oql = "Works where publication_year >= 2020"
        oqo = parse_oql_to_oqo(oql)
        
        f = oqo.filter_rows[0]
        assert f.column_id == "publication_year"
        assert f.value == 2020
    
    def test_parse_search_filter(self):
        """Test parsing search filter."""
        oql = 'Works where title & abstract contains "machine learning"'
        oqo = parse_oql_to_oqo(oql)
        
        f = oqo.filter_rows[0]
        assert f.column_id == "title_and_abstract.search"
        assert f.value == "machine learning"
        assert f.operator == "contains"
    
    def test_parse_null_value(self):
        """Test parsing null/unknown value."""
        oql = "Works where language is unknown"
        oqo = parse_oql_to_oqo(oql)
        
        f = oqo.filter_rows[0]
        assert f.value is None
    
    def test_parse_multiple_filters(self):
        """Test parsing multiple filters with 'and'."""
        oql = "Works where it's Open Access and year >= 2020 and Country is [countries/ca]"
        oqo = parse_oql_to_oqo(oql)
        
        assert len(oqo.filter_rows) == 3
    
    def test_parse_or_expression(self):
        """Test parsing OR expression in parentheses."""
        oql = "Works where (type is [types/article] or type is [types/book])"
        oqo = parse_oql_to_oqo(oql)
        
        assert len(oqo.filter_rows) == 1
        f = oqo.filter_rows[0]
        assert isinstance(f, BranchFilter)
        assert f.join == "or"
        assert len(f.filters) == 2
    
    def test_parse_sort(self):
        """Test parsing sort clause."""
        oql = "Works where it's Open Access; sort by citations desc"
        oqo = parse_oql_to_oqo(oql)
        
        assert oqo.sort_by_column == "cited_by_count"
        assert oqo.sort_by_order == "desc"
    
    def test_parse_sample(self):
        """Test parsing sample clause."""
        oql = "Works where year >= 2024; sample 100"
        oqo = parse_oql_to_oqo(oql)
        
        assert oqo.sample == 100
    
    def test_parse_sort_and_sample(self):
        """Test parsing both sort and sample."""
        oql = "Works where it's Open Access; sort by citations desc; sample 50"
        oqo = parse_oql_to_oqo(oql)
        
        assert oqo.sort_by_column == "cited_by_count"
        assert oqo.sort_by_order == "desc"
        assert oqo.sample == 50
    
    def test_parse_technical_format(self):
        """Test parsing technical format."""
        oql = "Works where open_access.is_oa is true and sustainable_development_goals.id is [sdgs/2] and authorships.countries is [countries/ca] and institutions.is_global_south is true and publication_year >= 2020"
        oqo = parse_oql_to_oqo(oql)
        
        assert oqo.get_rows == "works"
        assert len(oqo.filter_rows) == 5
    
    def test_parse_negation(self):
        """Test parsing negation."""
        oql = "Works where type is not [types/article]"
        oqo = parse_oql_to_oqo(oql)
        
        f = oqo.filter_rows[0]
        assert f.operator == "is not"
        assert f.value == "types/article"
    
    def test_parse_complex_human_readable(self):
        """Test parsing the human-readable example from the user's request."""
        oql = "Works where it's Open Access and Sustainable Development Goals is Zero Hunger [sdgs/2] and Country is Canada [countries/ca] and it's from Global South and year >= 2020"
        oqo = parse_oql_to_oqo(oql)
        
        assert oqo.get_rows == "works"
        assert len(oqo.filter_rows) == 5
        
        # Verify each filter
        column_ids = [f.column_id for f in oqo.filter_rows if isinstance(f, LeafFilter)]
        assert "open_access.is_oa" in column_ids
        assert "sustainable_development_goals.id" in column_ids
        assert "authorships.countries" in column_ids
        assert "institutions.is_global_south" in column_ids
        assert "publication_year" in column_ids


class TestRoundTrip:
    """Tests for round-trip conversions (OQO -> OQL -> OQO)."""
    
    def test_round_trip_boolean(self):
        """Test round-trip for boolean filter."""
        original = OQO(
            get_rows="works",
            filter_rows=[
                LeafFilter(column_id="open_access.is_oa", value=True)
            ]
        )
        
        oql = render_oqo_to_oql(original)
        parsed = parse_oql_to_oqo(oql)
        
        assert parsed.get_rows == original.get_rows
        assert len(parsed.filter_rows) == 1
        f = parsed.filter_rows[0]
        assert f.column_id == "open_access.is_oa"
        assert f.value is True
    
    def test_round_trip_entity_value(self):
        """Test round-trip for entity value."""
        original = OQO(
            get_rows="works",
            filter_rows=[
                LeafFilter(column_id="authorships.countries", value="countries/ca")
            ]
        )
        
        oql = render_oqo_to_oql(original)
        parsed = parse_oql_to_oqo(oql)
        
        f = parsed.filter_rows[0]
        assert f.column_id == "authorships.countries"
        assert f.value == "countries/ca"
    
    def test_round_trip_comparison(self):
        """Test round-trip for comparison filter."""
        original = OQO(
            get_rows="works",
            filter_rows=[
                LeafFilter(column_id="publication_year", value=2020, operator=">=")
            ]
        )
        
        oql = render_oqo_to_oql(original)
        parsed = parse_oql_to_oqo(oql)
        
        f = parsed.filter_rows[0]
        assert f.column_id == "publication_year"
        assert f.value == 2020
        assert f.operator == ">="
    
    def test_round_trip_complex(self):
        """Test round-trip for complex query."""
        original = OQO(
            get_rows="works",
            filter_rows=[
                LeafFilter(column_id="open_access.is_oa", value=True),
                LeafFilter(column_id="sustainable_development_goals.id", value="sdgs/2"),
                LeafFilter(column_id="authorships.countries", value="countries/ca"),
                LeafFilter(column_id="institutions.is_global_south", value=True),
                LeafFilter(column_id="publication_year", value=2020, operator=">=")
            ],
            sort_by_column="cited_by_count",
            sort_by_order="desc"
        )
        
        oql = render_oqo_to_oql(original)
        parsed = parse_oql_to_oqo(oql)
        
        assert parsed.get_rows == original.get_rows
        assert len(parsed.filter_rows) == len(original.filter_rows)
        assert parsed.sort_by_column == original.sort_by_column
        assert parsed.sort_by_order == original.sort_by_order


class TestEdgeCases:
    """Tests for edge cases and error handling."""
    
    def test_empty_string_raises(self):
        """Test that empty string raises error."""
        with pytest.raises(OQLParseError):
            parse_oql_to_oqo("")
    
    def test_unknown_column_passes_through(self):
        """Test that unknown column names pass through."""
        oql = "Works where unknown_column is value"
        oqo = parse_oql_to_oqo(oql)
        
        f = oqo.filter_rows[0]
        assert f.column_id == "unknown_column"
    
    def test_quoted_value_with_spaces(self):
        """Test parsing quoted values with spaces."""
        oql = 'Works where title & abstract contains "climate change adaptation"'
        oqo = parse_oql_to_oqo(oql)
        
        f = oqo.filter_rows[0]
        assert f.value == "climate change adaptation"
    
    def test_case_insensitive_keywords(self):
        """Test that keywords are case insensitive."""
        oql = "WORKS WHERE IT'S OPEN ACCESS AND YEAR >= 2020"
        oqo = parse_oql_to_oqo(oql)
        
        assert oqo.get_rows == "works"
        assert len(oqo.filter_rows) == 2
    
    def test_native_entity_without_display_name(self):
        """Test native entity ID without display name in brackets."""
        oql = "Works where institution is [institutions/I136199984]"
        oqo = parse_oql_to_oqo(oql)
        
        f = oqo.filter_rows[0]
        assert f.value == "institutions/I136199984"
    
    def test_renderer_handles_native_entity_without_resolver(self):
        """Test renderer handles native entity without display name resolver."""
        oqo = OQO(
            get_rows="works",
            filter_rows=[
                LeafFilter(column_id="authorships.institutions.lineage", value="institutions/I136199984")
            ]
        )
        result = render_oqo_to_oql(oqo)
        # Should fall back to just bracketed ID
        assert "[institutions/I136199984]" in result
