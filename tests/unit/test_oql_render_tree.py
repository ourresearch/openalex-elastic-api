"""
Tests for oql_render tree generation and stringify invariant.

Tests verify:
- Invariant A: stringify(oql_render) === oql
- Invariant B: parse roundtrip produces same canonical OQO
- Tree structure correctness
- Canonicalization behavior
"""

import pytest
from query_translation.oqo import OQO, LeafFilter, BranchFilter
from query_translation.oql_render_tree import (
    OQLRenderTree, EntityHead, GroupNode, ClauseNode, Segment, SegmentMeta,
    ClauseMeta, GroupMeta, EntityValue, SortDirective, SampleDirective,
    SortMeta, SampleMeta, stringify
)
from query_translation.oql_tree_renderer import render_oqo_to_oql_and_tree, OQLTreeRenderer
from query_translation.oqo_canonicalizer import canonicalize_oqo


class TestStringifyInvariant:
    """Tests for Invariant A: stringify(oql_render) === oql."""
    
    def test_simple_entity_only(self):
        """Test entity-only statement (no filters)."""
        oqo = OQO(get_rows="works", filter_rows=[])
        oql, tree = render_oqo_to_oql_and_tree(oqo)
        
        assert stringify(tree) == oql
        assert oql == "Works"
    
    def test_single_boolean_filter(self):
        """Test single boolean filter with 'it's' format."""
        oqo = OQO(
            get_rows="works",
            filter_rows=[LeafFilter(column_id="open_access.is_oa", value=True)]
        )
        oql, tree = render_oqo_to_oql_and_tree(oqo)
        
        assert stringify(tree) == oql
        assert "it's Open Access" in oql
    
    def test_single_comparison_filter(self):
        """Test comparison filter (year >= 2020)."""
        oqo = OQO(
            get_rows="works",
            filter_rows=[LeafFilter(column_id="publication_year", value=2020, operator=">=")]
        )
        oql, tree = render_oqo_to_oql_and_tree(oqo)
        
        assert stringify(tree) == oql
        assert "year >= 2020" in oql
    
    def test_entity_filter_with_display_name(self):
        """Test entity filter with resolved display name."""
        oqo = OQO(
            get_rows="works",
            filter_rows=[LeafFilter(column_id="authorships.countries", value="countries/ca")]
        )
        oql, tree = render_oqo_to_oql_and_tree(oqo)
        
        assert stringify(tree) == oql
        assert "Canada" in oql
        assert "[ca]" in oql
    
    def test_multiple_filters_with_and(self):
        """Test multiple filters joined with AND."""
        oqo = OQO(
            get_rows="works",
            filter_rows=[
                LeafFilter(column_id="open_access.is_oa", value=True),
                LeafFilter(column_id="publication_year", value=2020, operator=">=")
            ]
        )
        oql, tree = render_oqo_to_oql_and_tree(oqo)
        
        assert stringify(tree) == oql
        assert " and " in oql
    
    def test_or_group_filter(self):
        """Test OR group with parentheses."""
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
        oql, tree = render_oqo_to_oql_and_tree(oqo)
        
        assert stringify(tree) == oql
        assert "(" in oql
        assert " or " in oql
        assert ")" in oql
    
    def test_sort_directive(self):
        """Test sort directive."""
        oqo = OQO(
            get_rows="works",
            filter_rows=[],
            sort_by_column="cited_by_count",
            sort_by_order="desc"
        )
        oql, tree = render_oqo_to_oql_and_tree(oqo)
        
        assert stringify(tree) == oql
        assert "; sort by" in oql
    
    def test_sample_directive(self):
        """Test sample directive."""
        oqo = OQO(
            get_rows="works",
            filter_rows=[],
            sample=100
        )
        oql, tree = render_oqo_to_oql_and_tree(oqo)
        
        assert stringify(tree) == oql
        assert "; sample 100" in oql
    
    def test_complex_query(self):
        """Test complex query with filters, sort, and sample."""
        oqo = OQO(
            get_rows="works",
            filter_rows=[
                LeafFilter(column_id="open_access.is_oa", value=True),
                LeafFilter(column_id="publication_year", value=2020, operator=">="),
                BranchFilter(
                    join="or",
                    filters=[
                        LeafFilter(column_id="sustainable_development_goals.id", value="sdgs/2"),
                        LeafFilter(column_id="sustainable_development_goals.id", value="sdgs/4")
                    ]
                )
            ],
            sort_by_column="cited_by_count",
            sort_by_order="desc",
            sample=100
        )
        oql, tree = render_oqo_to_oql_and_tree(oqo)
        
        assert stringify(tree) == oql


class TestCanonicalization:
    """Tests for OQO canonicalization."""
    
    def test_string_boolean_to_bool(self):
        """Test that string 'true' is normalized to bool True."""
        oqo = OQO(
            get_rows="works",
            filter_rows=[LeafFilter(column_id="open_access.is_oa", value="true")]
        )
        
        canonical = canonicalize_oqo(oqo)
        
        assert canonical.filter_rows[0].value is True
    
    def test_string_integer_to_int(self):
        """Test that string '2020' is normalized to int 2020 for numeric columns."""
        oqo = OQO(
            get_rows="works",
            filter_rows=[LeafFilter(column_id="publication_year", value="2020", operator=">=")]
        )
        
        canonical = canonicalize_oqo(oqo)
        
        assert canonical.filter_rows[0].value == 2020
        assert isinstance(canonical.filter_rows[0].value, int)
    
    def test_entity_type_lowercase(self):
        """Test that entity type is normalized to lowercase."""
        oqo = OQO(get_rows="Works", filter_rows=[])
        
        canonical = canonicalize_oqo(oqo)
        
        assert canonical.get_rows == "works"
    
    def test_single_child_group_unwrapped(self):
        """Test that single-child groups are unwrapped."""
        oqo = OQO(
            get_rows="works",
            filter_rows=[
                BranchFilter(
                    join="or",
                    filters=[LeafFilter(column_id="type", value="article")]
                )
            ]
        )
        
        canonical = canonicalize_oqo(oqo)
        
        # Single-child OR group should become a simple leaf filter
        assert isinstance(canonical.filter_rows[0], LeafFilter)
    
    def test_nested_same_join_flattened(self):
        """Test that nested same-join groups are flattened."""
        oqo = OQO(
            get_rows="works",
            filter_rows=[
                BranchFilter(
                    join="and",
                    filters=[
                        LeafFilter(column_id="type", value="article"),
                        BranchFilter(
                            join="and",
                            filters=[
                                LeafFilter(column_id="publication_year", value=2020, operator=">="),
                                LeafFilter(column_id="publication_year", value=2024, operator="<=")
                            ]
                        )
                    ]
                )
            ]
        )
        
        canonical = canonicalize_oqo(oqo)
        
        # Should flatten to a single AND group with 3 children
        branch = canonical.filter_rows[0]
        assert isinstance(branch, BranchFilter)
        assert len(branch.filters) == 3


class TestTreeStructure:
    """Tests for oql_render tree structure."""
    
    def test_tree_has_version(self):
        """Test that tree includes version."""
        oqo = OQO(get_rows="works", filter_rows=[])
        _, tree = render_oqo_to_oql_and_tree(oqo)
        
        assert tree.version == "1.0"
    
    def test_tree_has_entity(self):
        """Test that tree includes entity head."""
        oqo = OQO(get_rows="works", filter_rows=[])
        _, tree = render_oqo_to_oql_and_tree(oqo)
        
        assert tree.entity.id == "works"
        assert tree.entity.text == "Works"
    
    def test_no_filters_has_null_where(self):
        """Test that no filters produces null where and empty keyword."""
        oqo = OQO(get_rows="works", filter_rows=[])
        _, tree = render_oqo_to_oql_and_tree(oqo)
        
        assert tree.where is None
        assert tree.where_keyword == ""
    
    def test_filters_has_where_keyword(self):
        """Test that filters produce ' where ' keyword."""
        oqo = OQO(
            get_rows="works",
            filter_rows=[LeafFilter(column_id="publication_year", value=2020, operator=">=")]
        )
        _, tree = render_oqo_to_oql_and_tree(oqo)
        
        assert tree.where is not None
        assert tree.where_keyword == " where "
    
    def test_clause_has_segments(self):
        """Test that clause nodes have segments."""
        oqo = OQO(
            get_rows="works",
            filter_rows=[LeafFilter(column_id="publication_year", value=2020, operator=">=")]
        )
        _, tree = render_oqo_to_oql_and_tree(oqo)
        
        clause = tree.where
        assert isinstance(clause, ClauseNode)
        assert len(clause.segments) > 0
    
    def test_clause_meta_has_semantics(self):
        """Test that clause meta contains semantic info."""
        oqo = OQO(
            get_rows="works",
            filter_rows=[LeafFilter(column_id="publication_year", value=2020, operator=">=")]
        )
        _, tree = render_oqo_to_oql_and_tree(oqo)
        
        clause = tree.where
        assert clause.meta.column_id == "publication_year"
        assert clause.meta.operator == ">="
        assert clause.meta.value == 2020
    
    def test_group_has_joiner(self):
        """Test that group nodes have explicit joiner."""
        oqo = OQO(
            get_rows="works",
            filter_rows=[
                LeafFilter(column_id="open_access.is_oa", value=True),
                LeafFilter(column_id="publication_year", value=2020, operator=">=")
            ]
        )
        _, tree = render_oqo_to_oql_and_tree(oqo)
        
        group = tree.where
        assert isinstance(group, GroupNode)
        assert group.joiner == " and "
    
    def test_or_group_has_parentheses(self):
        """Test that OR groups have parentheses."""
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
        _, tree = render_oqo_to_oql_and_tree(oqo)
        
        group = tree.where
        assert isinstance(group, GroupNode)
        assert group.prefix == "("
        assert group.suffix == ")"
        assert group.joiner == " or "


class TestToDict:
    """Tests for tree serialization to dict."""
    
    def test_tree_to_dict_has_required_fields(self):
        """Test that to_dict produces all required fields."""
        oqo = OQO(
            get_rows="works",
            filter_rows=[LeafFilter(column_id="publication_year", value=2020, operator=">=")],
            sort_by_column="cited_by_count",
            sort_by_order="desc"
        )
        _, tree = render_oqo_to_oql_and_tree(oqo)
        
        d = tree.to_dict()
        
        assert "version" in d
        assert "entity" in d
        assert "where_keyword" in d
        assert "where" in d
        assert "directives" in d
    
    def test_clause_to_dict(self):
        """Test clause serialization."""
        oqo = OQO(
            get_rows="works",
            filter_rows=[LeafFilter(column_id="publication_year", value=2020, operator=">=")]
        )
        _, tree = render_oqo_to_oql_and_tree(oqo)
        
        d = tree.to_dict()
        clause = d["where"]
        
        assert clause["type"] == "clause"
        assert "segments" in clause
        assert "meta" in clause
        assert clause["meta"]["column_id"] == "publication_year"


class TestEntityResolution:
    """Tests for entity display name resolution."""
    
    def test_country_resolution(self):
        """Test country code resolution."""
        oqo = OQO(
            get_rows="works",
            filter_rows=[LeafFilter(column_id="authorships.countries", value="countries/us")]
        )
        oql, _ = render_oqo_to_oql_and_tree(oqo)
        
        assert "United States" in oql
        assert "[us]" in oql
    
    def test_sdg_resolution(self):
        """Test SDG resolution."""
        oqo = OQO(
            get_rows="works",
            filter_rows=[LeafFilter(column_id="sustainable_development_goals.id", value="sdgs/4")]
        )
        oql, _ = render_oqo_to_oql_and_tree(oqo)
        
        assert "Quality Education" in oql
        assert "[4]" in oql
    
    def test_language_resolution(self):
        """Test language code resolution."""
        oqo = OQO(
            get_rows="works",
            filter_rows=[LeafFilter(column_id="language", value="languages/en")]
        )
        oql, _ = render_oqo_to_oql_and_tree(oqo)
        
        assert "English" in oql
        assert "[en]" in oql
    
    def test_type_resolution(self):
        """Test work type resolution."""
        oqo = OQO(
            get_rows="works",
            filter_rows=[LeafFilter(column_id="type", value="types/book-chapter")]
        )
        oql, _ = render_oqo_to_oql_and_tree(oqo)
        
        assert "Book Chapter" in oql


class TestEdgeCases:
    """Tests for edge cases."""
    
    def test_null_value(self):
        """Test null value rendering."""
        oqo = OQO(
            get_rows="works",
            filter_rows=[LeafFilter(column_id="language", value=None)]
        )
        oql, tree = render_oqo_to_oql_and_tree(oqo)
        
        assert stringify(tree) == oql
        assert "unknown" in oql
    
    def test_text_search_quoted(self):
        """Test text search values are quoted."""
        oqo = OQO(
            get_rows="works",
            filter_rows=[LeafFilter(column_id="title_and_abstract.search", value="machine learning", operator="contains")]
        )
        oql, tree = render_oqo_to_oql_and_tree(oqo)
        
        assert stringify(tree) == oql
        assert '"machine learning"' in oql
    
    def test_different_entity_types(self):
        """Test different entity types render correctly."""
        entity_types = [
            ("authors", "Authors"),
            ("institutions", "Institutions"),
            ("sources", "Sources"),
            ("source-types", "Source Types"),
        ]
        
        for entity_id, expected_text in entity_types:
            oqo = OQO(get_rows=entity_id, filter_rows=[])
            oql, tree = render_oqo_to_oql_and_tree(oqo)
            
            assert stringify(tree) == oql
            assert tree.entity.text == expected_text
