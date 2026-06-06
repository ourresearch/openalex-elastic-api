"""
Tests for OQL rendering and parsing.

Tests both the human-readable and technical formats, and round-trip conversions.
"""

import pytest
from query_translation.oqo import OQO, LeafFilter, BranchFilter, SortBy
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
        """Test entity values include display name before bracketed short ID."""
        oqo = OQO(
            get_rows="works",
            filter_rows=[
                LeafFilter(column_id="authorships.countries", value="ca")
            ]
        )
        result = render_oqo_to_oql(oqo)
        assert result == "Works where Country is Canada [ca]"

    def test_entity_value_sdg(self):
        """Test SDG entity value with display name and short ID."""
        oqo = OQO(
            get_rows="works",
            filter_rows=[
                LeafFilter(column_id="sustainable_development_goals.id", value="2")
            ]
        )
        result = render_oqo_to_oql(oqo)
        assert result == "Works where Sustainable Development Goals is Zero Hunger [2]"

    def test_entity_value_type(self):
        """Test work type entity value with short ID."""
        oqo = OQO(
            get_rows="works",
            filter_rows=[
                LeafFilter(column_id="type", value="article")
            ]
        )
        result = render_oqo_to_oql(oqo)
        assert result == "Works where type is Article [article]"
    
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
                LeafFilter(column_id="authorships.countries", value="ca")
            ]
        )
        result = render_oqo_to_oql(oqo)
        assert "it's Open Access" in result
        assert "year >= 2020" in result
        assert "Canada [ca]" in result
        assert " and " in result
    
    def test_or_branch_filter(self):
        """Test OR branch filters with parentheses."""
        oqo = OQO(
            get_rows="works",
            filter_rows=[
                BranchFilter(
                    join="or",
                    filters=[
                        LeafFilter(column_id="type", value="article"),
                        LeafFilter(column_id="type", value="book")
                    ]
                )
            ]
        )
        result = render_oqo_to_oql(oqo)
        assert result.startswith("Works where (")
        assert "Article [article]" in result
        assert "Book [book]" in result
        assert " or " in result
    
    def test_sort_with_display_name(self):
        """Test sort uses display name."""
        oqo = OQO(
            get_rows="works",
            filter_rows=[
                LeafFilter(column_id="open_access.is_oa", value=True)
            ],
            sort_by=[SortBy("cited_by_count", "desc")],
        )
        result = render_oqo_to_oql(oqo)
        assert "; sort by citations desc" in result

    def test_multi_column_sort_render_oql(self):
        """A multi-key sort renders comma-separated in tiebreaker order (#333)."""
        oqo = OQO(
            get_rows="works",
            sort_by=[
                SortBy("publication_year", "desc"),
                SortBy("cited_by_count", "desc"),
            ],
        )
        result = render_oqo_to_oql(oqo)
        assert "; sort by year desc, citations desc" in result
    
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
        """Test negation as is_negated polarity bit (new spec: one mechanism)."""
        oqo = OQO(
            get_rows="works",
            filter_rows=[
                LeafFilter(column_id="type", value="article", is_negated=True)
            ]
        )
        result = render_oqo_to_oql(oqo)
        assert "is not Article [article]" in result

    def test_complex_query(self):
        """Test the example from the user's request."""
        oqo = OQO(
            get_rows="works",
            filter_rows=[
                LeafFilter(column_id="open_access.is_oa", value=True),
                LeafFilter(column_id="sustainable_development_goals.id", value="2"),
                LeafFilter(column_id="authorships.countries", value="ca"),
                LeafFilter(column_id="institutions.is_global_south", value=True),
                LeafFilter(column_id="publication_year", value=2020, operator=">=")
            ]
        )
        result = render_oqo_to_oql(oqo)
        
        assert "it's Open Access" in result
        assert "Zero Hunger [2]" in result
        assert "Canada [ca]" in result
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
    
    def test_parse_bracketed_id_only_rejected(self):
        """A bracket-only value (`[countries/ca]`) is now an error (oxjob #376).

        Under the canonical grammar `[...]` is an *ignored annotation* and the ID
        is authoritative — it must be a bare token. A lone annotation with no bare
        value is the v1.1 footgun the engine deliberately rejects.
        """
        with pytest.raises(OQLParseError):
            parse_oql_to_oqo("Works where Country is [countries/ca]")

    def test_parse_country_canonical_id_first(self):
        """Canonical entity form is ID-first; the `[name]` is an ignored annotation."""
        oql = "Works where Country is CA [Canada]"
        oqo = parse_oql_to_oqo(oql)

        f = oqo.filter_rows[0]
        assert f.column_id == "authorships.countries"
        # Country codes canonicalize to uppercase (ISO convention).
        assert f.value == "CA"

    def test_parse_sdg_canonical_id_first(self):
        """SDG canonical form: bare id first, `[name]` ignored."""
        oql = "Works where SDG is 2 [Zero Hunger]"
        oqo = parse_oql_to_oqo(oql)

        f = oqo.filter_rows[0]
        assert f.column_id == "sustainable_development_goals.id"
        assert f.value == "2"
    
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
        """Test parsing search filter (canonical v2 search model, oxjob #376).

        A quoted phrase is *exact* (no-stem) → the `.search.exact` column, and the
        value keeps its quotes.
        """
        oql = 'Works where title & abstract contains "machine learning"'
        oqo = parse_oql_to_oqo(oql)

        f = oqo.filter_rows[0]
        assert f.column_id == "title_and_abstract.search.exact"
        assert f.value == '"machine learning"'
        assert f.operator == "contains"
    
    def test_parse_null_value(self):
        """Test parsing null/unknown value."""
        oql = "Works where language is unknown"
        oqo = parse_oql_to_oqo(oql)
        
        f = oqo.filter_rows[0]
        assert f.value is None
    
    def test_parse_multiple_filters(self):
        """Test parsing multiple filters with 'and'."""
        oql = "Works where it's Open Access and year >= 2020 and Country is CA [Canada]"
        oqo = parse_oql_to_oqo(oql)

        assert len(oqo.filter_rows) == 3

    def test_parse_or_expression(self):
        """Test parsing OR expression in parentheses."""
        oql = "Works where (type is article or type is book)"
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

        assert oqo.sort_by == [SortBy("cited_by_count", "desc")]

    def test_parse_multi_column_sort(self):
        """A comma-separated OQL sort clause parses to an ordered list (#333)."""
        oql = "Works; sort by year desc, citations desc"
        oqo = parse_oql_to_oqo(oql)

        assert oqo.sort_by == [
            SortBy("publication_year", "desc"),
            SortBy("cited_by_count", "desc"),
        ]

    def test_parse_sample(self):
        """Test parsing sample clause."""
        oql = "Works where year >= 2024; sample 100"
        oqo = parse_oql_to_oqo(oql)
        
        assert oqo.sample == 100
    
    def test_parse_sort_and_sample(self):
        """Test parsing both sort and sample."""
        oql = "Works where it's Open Access; sort by citations desc; sample 50"
        oqo = parse_oql_to_oqo(oql)

        assert oqo.sort_by == [SortBy("cited_by_count", "desc")]
        assert oqo.sample == 50
    
    def test_parse_technical_format(self):
        """Test parsing technical (column-id) field names with bare values."""
        oql = "Works where open_access.is_oa is true and sustainable_development_goals.id is 2 and authorships.countries is CA and institutions.is_global_south is true and publication_year >= 2020"
        oqo = parse_oql_to_oqo(oql)

        assert oqo.get_rows == "works"
        assert len(oqo.filter_rows) == 5

    def test_parse_negation(self):
        """Test parsing negation."""
        oql = "Works where type is not article"
        oqo = parse_oql_to_oqo(oql)

        f = oqo.filter_rows[0]
        # New spec: negation is the is_negated polarity bit, not an operator;
        # value is bare (namespace lives on column_id).
        assert f.operator == "is"
        assert f.is_negated is True
        assert f.value == "article"

    def test_parse_complex_human_readable(self):
        """Test parsing a human-readable example (canonical id-first entity form)."""
        oql = "Works where it's Open Access and SDG is 2 [Zero Hunger] and Country is CA [Canada] and it's from Global South and year >= 2020"
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
    
    def test_parse_short_id_country(self):
        """Canonical id-first form: bare code, `[name]` is an ignored annotation."""
        oql = "Works where Country is CA [Canada]"
        oqo = parse_oql_to_oqo(oql)

        f = oqo.filter_rows[0]
        assert f.column_id == "authorships.countries"
        assert f.value == "CA"  # ISO code, uppercase-canonical

    def test_parse_short_id_sdg(self):
        """Canonical id-first SDG form."""
        oql = "Works where SDG is 2 [Zero Hunger]"
        oqo = parse_oql_to_oqo(oql)

        f = oqo.filter_rows[0]
        assert f.column_id == "sustainable_development_goals.id"
        assert f.value == "2"

    def test_parse_short_id_type(self):
        """Canonical type form: bare slug (a lone `[article]` annotation is rejected)."""
        oql = "Works where type is article"
        oqo = parse_oql_to_oqo(oql)

        f = oqo.filter_rows[0]
        assert f.column_id == "type"
        assert f.value == "article"

    def test_parse_short_id_institution(self):
        """Canonical id-first institution form: bare ID, `[name]` ignored."""
        oql = "Works where institution is I136199984 [Harvard University]"
        oqo = parse_oql_to_oqo(oql)

        f = oqo.filter_rows[0]
        assert f.column_id == "authorships.institutions.lineage"
        assert f.value == "I136199984"

    def test_parse_complex_with_short_ids(self):
        """Test parsing a complex query in the canonical id-first form."""
        oql = "Works where it's Open Access and SDG is 2 [Zero Hunger] and Country is CA [Canada] and it's from Global South and year >= 2020"
        oqo = parse_oql_to_oqo(oql)

        assert oqo.get_rows == "works"
        assert len(oqo.filter_rows) == 5

        values = {f.column_id: f.value for f in oqo.filter_rows if isinstance(f, LeafFilter)}
        assert values["sustainable_development_goals.id"] == "2"
        assert values["authorships.countries"] == "CA"


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
    
    @pytest.mark.xfail(
        reason="oxjob #376 Phase-1 window: the live parser is the canonical engine "
        "(id-first entity convention) but render_oqo_to_oql is still the OLD name-first "
        "renderer (`Canada [ca]`), which the engine reads as value=CANADA. Phase 2 flips "
        "render to id-first and this round-trip closes. See EXPLORE.md §9.",
        strict=True,
    )
    def test_round_trip_entity_value(self):
        """Test round-trip for entity value (bare per new spec)."""
        original = OQO(
            get_rows="works",
            filter_rows=[
                LeafFilter(column_id="authorships.countries", value="ca")
            ]
        )

        oql = render_oqo_to_oql(original)
        parsed = parse_oql_to_oqo(oql)

        f = parsed.filter_rows[0]
        assert f.column_id == "authorships.countries"
        assert f.value == "ca"
    
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
    
    @pytest.mark.xfail(
        reason="oxjob #376 Phase-1 window: OLD name-first render vs canonical engine for "
        "the entity/country filters in this query (see test_round_trip_entity_value). "
        "Phase 2 render flip closes it. See EXPLORE.md §9.",
        strict=True,
    )
    def test_round_trip_complex(self):
        """Test round-trip for complex query."""
        original = OQO(
            get_rows="works",
            filter_rows=[
                LeafFilter(column_id="open_access.is_oa", value=True),
                LeafFilter(column_id="sustainable_development_goals.id", value="2"),
                LeafFilter(column_id="authorships.countries", value="ca"),
                LeafFilter(column_id="institutions.is_global_south", value=True),
                LeafFilter(column_id="publication_year", value=2020, operator=">=")
            ],
            sort_by=[SortBy("cited_by_count", "desc")],
        )
        
        oql = render_oqo_to_oql(original)
        parsed = parse_oql_to_oqo(oql)
        
        assert parsed.get_rows == original.get_rows
        assert len(parsed.filter_rows) == len(original.filter_rows)
        assert parsed.sort_by == original.sort_by


class TestEdgeCases:
    """Tests for edge cases and error handling."""
    
    def test_empty_string_raises(self):
        """Test that empty string raises error."""
        with pytest.raises(OQLParseError):
            parse_oql_to_oqo("")
    
    def test_unknown_column_rejected(self):
        """Unknown field names are now a loud error (oxjob #376).

        The canonical engine validates fields against the registry; an unknown
        field raises rather than silently passing a bogus column through to ES
        (the old v1.1 footgun). Loud-and-named beats silent-and-wrong.
        """
        with pytest.raises(OQLParseError):
            parse_oql_to_oqo("Works where unknown_column is value")

    def test_quoted_value_with_spaces(self):
        """A quoted multi-word phrase is exact (`.search.exact`) and keeps its quotes."""
        oql = 'Works where title & abstract contains "climate change adaptation"'
        oqo = parse_oql_to_oqo(oql)

        f = oqo.filter_rows[0]
        assert f.column_id == "title_and_abstract.search.exact"
        assert f.value == '"climate change adaptation"'
    
    def test_case_insensitive_keywords(self):
        """Test that keywords are case insensitive."""
        oql = "WORKS WHERE IT'S OPEN ACCESS AND YEAR >= 2020"
        oqo = parse_oql_to_oqo(oql)
        
        assert oqo.get_rows == "works"
        assert len(oqo.filter_rows) == 2
    
    def test_native_entity_bare_id(self):
        """A native entity reference is a bare ID (a lone `[...]` annotation is rejected)."""
        oql = "Works where institution is I136199984"
        oqo = parse_oql_to_oqo(oql)

        f = oqo.filter_rows[0]
        assert f.value == "I136199984"
    
    def test_renderer_handles_native_entity_without_resolver(self):
        """Test renderer handles native entity without display name resolver."""
        oqo = OQO(
            get_rows="works",
            filter_rows=[
                LeafFilter(column_id="authorships.institutions.lineage", value="I136199984")
            ]
        )
        result = render_oqo_to_oql(oqo)
        # Should fall back to just the short ID (without brackets)
        assert "I136199984" in result
