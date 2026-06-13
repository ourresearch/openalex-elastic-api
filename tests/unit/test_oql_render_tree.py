"""
Tests for oql_render tree generation and stringify invariant.

Tests verify:
- Invariant A: stringify(oql_render) === oql
- Invariant B: parse roundtrip produces same canonical OQO
- Tree structure correctness
- Canonicalization behavior
"""

import pytest
from query_translation.oqo import OQO, LeafFilter, BranchFilter, SortBy
from query_translation.oql_render_tree import (
    OQLRenderTree, EntityHead, GroupNode, ClauseNode, Segment, SegmentMeta,
    ClauseMeta, GroupMeta, EntityValue, SortDirective, SampleDirective,
    SortMeta, SampleMeta, stringify
)
from query_translation.oql_tree_renderer import render_oqo_to_oql_and_tree
from query_translation.oqo_canonicalizer import canonicalize_oqo


class TestStringifyInvariant:
    """Tests for Invariant A: stringify(oql_render) === oql."""
    
    def test_simple_entity_only(self):
        """Test entity-only statement (no filters)."""
        oqo = OQO(get_rows="works", filter_rows=[])
        oql, tree = render_oqo_to_oql_and_tree(oqo)
        
        assert stringify(tree) == oql
        assert oql == "works"

    def test_single_boolean_filter(self):
        """Test single boolean filter with canonical 'it's' phrase."""
        oqo = OQO(
            get_rows="works",
            filter_rows=[LeafFilter(column_id="open_access.is_oa", value=True)]
        )
        oql, tree = render_oqo_to_oql_and_tree(oqo)

        assert stringify(tree) == oql
        assert "it's open access" in oql
    
    def test_single_comparison_filter(self):
        """A numeric bound renders as an inequality clause: `year >= 2020` (oxjob
        #363 — the dash range literal was removed in decision 24; a closed range is
        two endpoint clauses `year >= 2019 and year <= 2023`)."""
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
            filter_rows=[LeafFilter(column_id="authorships.countries", value="ca")]
        )
        oql, tree = render_oqo_to_oql_and_tree(oqo)
        
        assert stringify(tree) == oql
        # Canonical id-first: value first, resolved name in brackets.
        assert "country is ca [Canada]" in oql
    
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
        """A same-column OR factors into a canonical `is (a or b)` group (#363)."""
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
        oql, tree = render_oqo_to_oql_and_tree(oqo)

        assert stringify(tree) == oql
        assert "type is (article or book)" in oql
    
    def test_sort_directive(self):
        """Test sort directive."""
        oqo = OQO(
            get_rows="works",
            filter_rows=[],
            sort_by=[SortBy("cited_by_count", "desc")],
        )
        oql, tree = render_oqo_to_oql_and_tree(oqo)

        assert stringify(tree) == oql
        assert "sort by" in oql
        assert ";" not in oql

    def test_multi_column_sort_directive(self):
        """A multi-key sort renders one directive; stringify is invariant (#333)."""
        oqo = OQO(
            get_rows="works",
            filter_rows=[],
            sort_by=[
                SortBy("publication_year", "desc"),
                SortBy("cited_by_count", "desc"),
            ],
        )
        oql, tree = render_oqo_to_oql_and_tree(oqo)

        assert stringify(tree) == oql
        assert "sort by" in oql
        assert ";" not in oql
        # Both keys present, in order, comma-separated.
        sort_directive = next(d for d in tree.directives if d.type == "sort")
        assert [k["column_id"] for k in sort_directive.meta.keys] == [
            "publication_year", "cited_by_count",
        ]
    
    def test_sample_directive(self):
        """Test sample directive."""
        oqo = OQO(
            get_rows="works",
            filter_rows=[],
            sample=100
        )
        oql, tree = render_oqo_to_oql_and_tree(oqo)
        
        assert stringify(tree) == oql
        assert "sample 100" in oql
        assert ";" not in oql
    
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
                        LeafFilter(column_id="sustainable_development_goals.id", value="2"),
                        LeafFilter(column_id="sustainable_development_goals.id", value="4")
                    ]
                )
            ],
            sort_by=[SortBy("cited_by_count", "desc")],
            sample=100
        )
        oql, tree = render_oqo_to_oql_and_tree(oqo)

        # This query exceeds the 80-col target, so render() lays it out
        # multi-line (#376 Phase 2). Invariant A generalizes:
        #  - the flat path of the formatter still equals stringify(tree), and
        #  - the multi-line form round-trips to the same canonical OQO.
        from query_translation.oql_lang import format_oql
        from query_translation.oqo_canonicalizer import canonicalize_oqo
        from tests.oql.oql_v2 import parse
        assert "\n" in oql
        assert stringify(tree) == format_oql(tree, width=10_000)
        assert canonicalize_oqo(parse(oql)).to_dict() == canonicalize_oqo(oqo).to_dict()


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
    
    def test_country_code_uppercased(self):
        """Country codes canonicalize to uppercase (matching the parser), so an
        OQO-JSON submit of country=ca is stable and won't miss the indexed CA."""
        oqo = OQO(
            get_rows="works",
            filter_rows=[LeafFilter(column_id="authorships.countries", value="ca")]
        )

        canonical = canonicalize_oqo(oqo)

        assert canonical.filter_rows[0].value == "CA"

    def test_enum_slug_lowercased(self):
        """Enum slug values canonicalize to lowercase (e.g. type=Article -> article)."""
        oqo = OQO(
            get_rows="works",
            filter_rows=[LeafFilter(column_id="type", value="Article")]
        )

        canonical = canonicalize_oqo(oqo)

        assert canonical.filter_rows[0].value == "article"

    def test_canonicalize_matches_parser_casing(self):
        """The canonicalizer's value-casing must match the parser's, so an OQO-JSON
        submit and the equivalent OQL parse converge on one canonical OQO."""
        from tests.oql.oql_v2 import parse
        submitted = OQO(
            get_rows="works",
            filter_rows=[LeafFilter(column_id="authorships.countries", value="ca")]
        )
        parsed = parse("works where country is ca")
        assert canonicalize_oqo(submitted).to_dict() == canonicalize_oqo(parsed).to_dict()

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

        # A top-level AND (filter_rows is itself an implicit AND) is hoisted into
        # separate rows (#363), and the nested AND flattens too -> 3 leaf rows.
        assert len(canonical.filter_rows) == 3
        assert all(isinstance(f, LeafFilter) for f in canonical.filter_rows)


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
        assert tree.entity.text == "works"
    
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
        """A nested OR group is parenthesized.

        Two *different* columns so the OR stays a genuine boolean group (a
        same-column OR would factor into `is any of (...)`), and it's nested
        under an AND so it isn't the unparenthesized top-level expression.
        """
        oqo = OQO(
            get_rows="works",
            filter_rows=[
                LeafFilter(column_id="open_access.is_oa", value=True),
                BranchFilter(
                    join="or",
                    filters=[
                        LeafFilter(column_id="type", value="article"),
                        LeafFilter(column_id="publication_year", value=2020, operator=">=")
                    ]
                )
            ]
        )
        _, tree = render_oqo_to_oql_and_tree(oqo)

        and_group = tree.where
        assert isinstance(and_group, GroupNode)
        or_group = next(c for c in and_group.children if isinstance(c, GroupNode))
        assert or_group.prefix == "("
        assert or_group.suffix == ")"
        assert or_group.joiner == " or "


class TestToDict:
    """Tests for tree serialization to dict."""
    
    def test_tree_to_dict_has_required_fields(self):
        """Test that to_dict produces all required fields."""
        oqo = OQO(
            get_rows="works",
            filter_rows=[LeafFilter(column_id="publication_year", value=2020, operator=">=")],
            sort_by=[SortBy("cited_by_count", "desc")],
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
            filter_rows=[LeafFilter(column_id="authorships.countries", value="us")]
        )
        oql, _ = render_oqo_to_oql_and_tree(oqo)

        # Canonical id-first: code first, resolved name in brackets.
        assert "country is us [United States]" in oql

    def test_sdg_resolution(self):
        """Test SDG resolution (id-first)."""
        oqo = OQO(
            get_rows="works",
            filter_rows=[LeafFilter(column_id="sustainable_development_goals.id", value="4")]
        )
        oql, _ = render_oqo_to_oql_and_tree(oqo)

        assert "SDG is 4 [Quality education]" in oql  # name from config/sdgs.yaml (#363)

    def test_language_name_resolved(self):
        """Language resolves a [display name] from config/languages.yaml — it's a
        closed code vocabulary, not a 'super obvious' enum (oxjob #363 case 5)."""
        oqo = OQO(
            get_rows="works",
            filter_rows=[LeafFilter(column_id="language", value="en")]
        )
        oql, _ = render_oqo_to_oql_and_tree(oqo)

        assert oql == "works where language is en [English]"

    def test_type_rendered_bare(self):
        """Work type is a canonical enum slug — rendered bare, no name annotation."""
        oqo = OQO(
            get_rows="works",
            filter_rows=[LeafFilter(column_id="type", value="book-chapter")]
        )
        oql, _ = render_oqo_to_oql_and_tree(oqo)

        assert oql == "works where type is book-chapter"


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
    
    def test_text_search_stemmed_bare(self):
        """A stemmed search value renders bare (canonical) — no auto-quoting."""
        oqo = OQO(
            get_rows="works",
            filter_rows=[LeafFilter(column_id="title_and_abstract.search", value="machine learning", operator="contains")]
        )
        oql, tree = render_oqo_to_oql_and_tree(oqo)

        assert stringify(tree) == oql
        assert "contains machine learning" in oql

    def test_different_entity_types(self):
        """Test different entity types render correctly (lowercase, canonical)."""
        entity_types = [
            ("authors", "authors"),
            ("institutions", "institutions"),
            ("sources", "sources"),
            ("source-types", "source-types"),
        ]

        for entity_id, expected_text in entity_types:
            oqo = OQO(get_rows=entity_id, filter_rows=[])
            oql, tree = render_oqo_to_oql_and_tree(oqo)

            assert stringify(tree) == oql
            assert tree.entity.text == expected_text
