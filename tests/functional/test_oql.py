"""
Tests for OQL rendering and parsing.

Tests both the human-readable and technical formats, and round-trip conversions.
"""

import pytest
from query_translation.oqo import OQO, LeafFilter, BranchFilter, SortBy
from query_translation.oqo_canonicalizer import canonicalize_oqo
from query_translation.oql_renderer import render_oqo_to_oql
from query_translation.oql_parser import parse_oql_to_oqo, OQLParseError


class TestOQLRenderer:
    """Tests for OQO -> canonical OQL rendering (oxjob #376: the renderer now
    delegates to the one engine, so output is the canonical form — lowercase
    entity head + boolean phrasing, id-first entity values with the resolved
    name in brackets, bare enum slugs, same-field OR factored to `any of`)."""

    def test_simple_entity_type(self):
        """Entity head renders lowercase (canonical)."""
        oqo = OQO(get_rows="works")
        result = render_oqo_to_oql(oqo)
        assert result == "works"

    def test_entity_type_with_hyphen(self):
        """Hyphenated entity types keep their slug, lowercase."""
        oqo = OQO(get_rows="source-types")
        result = render_oqo_to_oql(oqo)
        assert result == "source-types"

    def test_boolean_filter_true(self):
        """Boolean true renders as the canonical 'it's …' phrase."""
        oqo = OQO(
            get_rows="works",
            filter_rows=[
                LeafFilter(column_id="open_access.is_oa", value=True)
            ]
        )
        result = render_oqo_to_oql(oqo)
        assert result == "works where it's open access"

    def test_boolean_filter_false(self):
        """Boolean false renders as the canonical 'it's not …' phrase."""
        oqo = OQO(
            get_rows="works",
            filter_rows=[
                LeafFilter(column_id="open_access.is_oa", value=False)
            ]
        )
        result = render_oqo_to_oql(oqo)
        assert result == "works where it's not open access"

    def test_boolean_filter_global_south(self):
        """Global South boolean uses the engine's canonical phrase."""
        oqo = OQO(
            get_rows="works",
            filter_rows=[
                LeafFilter(column_id="institutions.is_global_south", value=True)
            ]
        )
        result = render_oqo_to_oql(oqo)
        assert result == "works where it's from the global south"

    def test_entity_value_with_display_name(self):
        """Entity values are id-first; the resolved name goes in brackets."""
        oqo = OQO(
            get_rows="works",
            filter_rows=[
                LeafFilter(column_id="authorships.countries", value="ca")
            ]
        )
        result = render_oqo_to_oql(oqo)
        assert result == "works where country is ca [Canada]"

    def test_entity_value_sdg(self):
        """SDG: bare id first, resolved name in brackets."""
        oqo = OQO(
            get_rows="works",
            filter_rows=[
                LeafFilter(column_id="sustainable_development_goals.id", value="2")
            ]
        )
        result = render_oqo_to_oql(oqo)
        assert result == "works where SDG is 2 [Zero hunger]"

    def test_entity_value_type(self):
        """Enum slugs (type) render bare — no name annotation (canonical)."""
        oqo = OQO(
            get_rows="works",
            filter_rows=[
                LeafFilter(column_id="type", value="article")
            ]
        )
        result = render_oqo_to_oql(oqo)
        assert result == "works where type is article"

    def test_comparison_filter(self):
        """Test comparison filters use display names."""
        oqo = OQO(
            get_rows="works",
            filter_rows=[
                LeafFilter(column_id="publication_year", value=2020, operator=">=")
            ]
        )
        result = render_oqo_to_oql(oqo)
        assert result == "works where year >= 2020"

    def test_search_filter(self):
        """A stemmed search value renders bare (no quotes) in canonical form."""
        oqo = OQO(
            get_rows="works",
            filter_rows=[
                LeafFilter(column_id="title_and_abstract.search", value="machine learning", operator="contains")
            ]
        )
        result = render_oqo_to_oql(oqo)
        assert result == 'works where title & abstract contains machine learning'

    def test_null_value(self):
        """Test null values render as 'unknown'."""
        oqo = OQO(
            get_rows="works",
            filter_rows=[
                LeafFilter(column_id="language", value=None)
            ]
        )
        result = render_oqo_to_oql(oqo)
        assert result == "works where language is unknown"

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
        assert "it's open access" in result
        assert "year >= 2020" in result
        assert "country is ca [Canada]" in result
        assert " and " in result

    def test_or_branch_filter(self):
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
        result = render_oqo_to_oql(oqo)
        assert result == "works where type is (article or book)"

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
        assert "sort by citations desc" in result
        assert ";" not in result

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
        assert "sort by year desc, citations desc" in result
        assert ";" not in result

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
        assert "sample 100" in result
        assert ";" not in result

    def test_negation(self):
        """Negation is the is_negated polarity bit; enum slug renders bare."""
        oqo = OQO(
            get_rows="works",
            filter_rows=[
                LeafFilter(column_id="type", value="article", is_negated=True)
            ]
        )
        result = render_oqo_to_oql(oqo)
        assert "type is not article" in result

    def test_complex_query(self):
        """Test the example from the user's request (canonical forms)."""
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

        assert "it's open access" in result
        assert "SDG is 2 [Zero hunger]" in result
        assert "country is ca [Canada]" in result
        assert "it's from the global south" in result
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

    def test_parse_directives_without_semicolons(self):
        """Directives now read without `;` separators (oxjob #377); the `;` form
        still parses (back-compat) and yields an identical OQO."""
        without = parse_oql_to_oqo(
            "Works where it's Open Access sort by citations desc sample 50")
        with_semis = parse_oql_to_oqo(
            "Works where it's Open Access; sort by citations desc; sample 50")
        assert without.to_dict() == with_semis.to_dict()
        assert without.sort_by == [SortBy("cited_by_count", "desc")]
        assert without.sample == 50

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
    
    def test_round_trip_entity_value(self):
        """Round-trip for an entity value, now closed (oxjob #376 render merge).

        Render is the canonical id-first form (`country is CA [Canada]`); the
        `[Canada]` is an ignored annotation and `CA` is authoritative, so
        OQO -> OQL -> OQO is the identity on the canonicalized OQO. (Country
        codes canonicalize to uppercase.)
        """
        # Country codes are uppercase in the engine's canonical form (the parser
        # uppercases bare codes), so start from "CA".
        original = canonicalize_oqo(OQO(
            get_rows="works",
            filter_rows=[
                LeafFilter(column_id="authorships.countries", value="CA")
            ]
        ))

        oql = render_oqo_to_oql(original)
        parsed = canonicalize_oqo(parse_oql_to_oqo(oql))

        f = parsed.filter_rows[0]
        assert f.column_id == "authorships.countries"
        assert f.value == "CA"
        assert parsed.to_dict() == original.to_dict()

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
        """Round-trip for a complex query, now closed (oxjob #376 render merge).

        Canonical id-first render means OQO -> OQL -> OQO is the identity on the
        canonicalized OQO, entity/country filters included.
        """
        original = canonicalize_oqo(OQO(
            get_rows="works",
            filter_rows=[
                LeafFilter(column_id="open_access.is_oa", value=True),
                LeafFilter(column_id="sustainable_development_goals.id", value="2"),
                LeafFilter(column_id="authorships.countries", value="CA"),
                LeafFilter(column_id="institutions.is_global_south", value=True),
                LeafFilter(column_id="publication_year", value=2020, operator=">=")
            ],
            sort_by=[SortBy("cited_by_count", "desc")],
        ))

        oql = render_oqo_to_oql(original)
        parsed = canonicalize_oqo(parse_oql_to_oqo(oql))

        assert parsed.get_rows == original.get_rows
        assert len(parsed.filter_rows) == len(original.filter_rows)
        assert parsed.sort_by == original.sort_by
        assert parsed.to_dict() == original.to_dict()


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
