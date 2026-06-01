"""
Tests for query format translation.

Tests cover:
- Round-trip tests (URL → OQO → URL)
- OQO parsing and validation
- Three-way equivalence tests
- Error cases
"""

import pytest
from query_translation.oqo import OQO, LeafFilter, BranchFilter, filter_from_dict
from query_translation.url_parser import parse_url_to_oqo, parse_filter_string
from query_translation.url_renderer import render_oqo_to_url, URLRenderError
from query_translation.validator import validate_oqo


class TestURLParser:
    """Tests for URL → OQO parsing."""
    
    def test_simple_filter(self):
        """Test parsing a simple single filter."""
        oqo = parse_url_to_oqo("works", filter_string="type:article")
        
        assert oqo.get_rows == "works"
        assert len(oqo.filter_rows) == 1
        assert oqo.filter_rows[0].column_id == "type"
        assert oqo.filter_rows[0].value == "article"
        assert oqo.filter_rows[0].operator == "is"
    
    def test_multiple_filters(self):
        """Test parsing multiple filters (AND)."""
        oqo = parse_url_to_oqo(
            "works", 
            filter_string="type:article,publication_year:2024"
        )
        
        assert len(oqo.filter_rows) == 2
    
    def test_or_filter(self):
        """Test parsing OR filter with pipe."""
        oqo = parse_url_to_oqo("works", filter_string="type:article|book")
        
        assert len(oqo.filter_rows) == 1
        branch = oqo.filter_rows[0]
        assert isinstance(branch, BranchFilter)
        assert branch.join == "or"
        assert len(branch.filters) == 2
    
    def test_negation_filter(self):
        """Test parsing negation with !."""
        oqo = parse_url_to_oqo("works", filter_string="type:!article")

        assert oqo.filter_rows[0].operator == "is"
        assert oqo.filter_rows[0].is_negated is True
        assert oqo.filter_rows[0].value == "article"
    
    def test_range_gte(self):
        """Test parsing >= range (trailing dash)."""
        oqo = parse_url_to_oqo("works", filter_string="publication_year:2024-")
        
        assert oqo.filter_rows[0].operator == ">="
        assert oqo.filter_rows[0].value == "2024"
    
    def test_range_lte(self):
        """Test parsing <= range (leading dash)."""
        oqo = parse_url_to_oqo("works", filter_string="cited_by_count:-100")
        
        assert oqo.filter_rows[0].operator == "<="
        assert oqo.filter_rows[0].value == "100"
    
    def test_range_both(self):
        """Test parsing bounded range."""
        oqo = parse_url_to_oqo("works", filter_string="publication_year:2020-2024")
        
        # Should create two filters: >= 2020 AND <= 2024
        assert len(oqo.filter_rows) == 2
        operators = {f.operator for f in oqo.filter_rows}
        assert operators == {">=", "<="}
    
    def test_issn_hyphen_is_exact_not_range(self):
        """ISSN values are `NNNN-NNNN`; the hyphen must NOT be read as a range.

        Regression for the column-type-aware range fix (oxjob #323): range-ness
        is a column property, not a value shape. `issn` columns are string/term
        columns (no `range` operator), so `0021-9258` is one exact filter, not
        `>=0021 AND <=9258`. Verified against real corpus URLs.
        """
        for entity, col in [
            ("sources", "issn"),
            ("works", "primary_location.source.issn"),
            ("works", "locations.source.issn"),
        ]:
            oqo = parse_url_to_oqo(entity, filter_string=f"{col}:0021-9258")
            assert len(oqo.filter_rows) == 1, (entity, col, oqo.filter_rows)
            leaf = oqo.filter_rows[0]
            assert leaf.column_id == col
            assert leaf.operator == "is"
            assert leaf.value == "0021-9258"
            assert validate_oqo(oqo).valid

    def test_numeric_and_date_columns_still_range(self):
        """The fix must not regress real range columns (numeric/date)."""
        oqo = parse_url_to_oqo("works", filter_string="cited_by_count:100-500")
        assert {f.operator for f in oqo.filter_rows} == {">=", "<="}

        oqo = parse_url_to_oqo("works", filter_string="publication_year:2020-")
        assert len(oqo.filter_rows) == 1
        assert oqo.filter_rows[0].operator == ">="

    def test_issn_and_year_range_in_one_filter(self):
        """Mixed real-world filter: exact ISSN AND a year range coexist."""
        oqo = parse_url_to_oqo(
            "works",
            filter_string="primary_location.source.issn:0964-6639,publication_year:2020-2024",
        )
        ops = [(r.column_id, r.operator) for r in oqo.filter_rows]
        assert ("primary_location.source.issn", "is") in ops
        assert ("publication_year", ">=") in ops
        assert ("publication_year", "<=") in ops
        assert validate_oqo(oqo).valid

    def test_range_parsing_without_entity_keeps_shape_behavior(self):
        """`parse_filter_string` with no entity context is unchanged (back-compat)."""
        rows = parse_filter_string("issn:0021-9258")  # no entity_type
        assert {r.operator for r in rows} == {">=", "<="}

    def test_null_value(self):
        """Test parsing null value."""
        oqo = parse_url_to_oqo("works", filter_string="language:null")
        
        assert oqo.filter_rows[0].value is None
        assert oqo.filter_rows[0].operator == "is"
    
    def test_not_null_value(self):
        """Test parsing !null value."""
        oqo = parse_url_to_oqo("works", filter_string="language:!null")

        assert oqo.filter_rows[0].value is None
        assert oqo.filter_rows[0].operator == "is"
        assert oqo.filter_rows[0].is_negated is True
    
    def test_boolean_value(self):
        """Test parsing boolean value."""
        oqo = parse_url_to_oqo("works", filter_string="is_oa:true")
        
        assert oqo.filter_rows[0].value == "true"
    
    def test_sort_parsing(self):
        """Test parsing sort parameter."""
        oqo = parse_url_to_oqo(
            "works",
            filter_string="type:article",
            sort_string="cited_by_count:desc"
        )
        
        assert oqo.sort_by_column == "cited_by_count"
        assert oqo.sort_by_order == "desc"

    def test_directionless_sort_defaults_asc(self):
        """A sort with no `:dir` must default to `asc`, matching legacy
        core/utils.py:map_sort_params. A `desc` default silently reversed the
        page vs the legacy URL path (oxjob #323 Pattern F1)."""
        oqo = parse_url_to_oqo("works", sort_string="publication_date")
        assert oqo.sort_by_column == "publication_date"
        assert oqo.sort_by_order == "asc"

    def test_negated_or_list_negates_whole_list(self):
        """`field:!a|b|c` means NOT (a OR b OR c), not `(NOT a) OR b OR c`.

        Legacy core/filter.py negates every value after a leading `!` and ANDs
        them (NOT IN list). The OQO must be a *negated* OR-branch over positive
        leaves; mis-parsing it as an OR of mixed-polarity leaves over-counts to
        nearly the whole index (oxjob #323 Pattern D negated OR-list)."""
        oqo = parse_url_to_oqo(
            "works",
            filter_string="primary_location.source.id:!s1|s2|s3",
        )
        assert len(oqo.filter_rows) == 1
        branch = oqo.filter_rows[0]
        assert branch.join == "or"
        assert branch.is_negated is True
        assert [leaf.value for leaf in branch.filters] == ["s1", "s2", "s3"]
        # leaves are positive — the polarity lives on the branch (NNF before canon)
        assert all(leaf.is_negated is False for leaf in branch.filters)
        assert validate_oqo(oqo).valid

    def test_positive_or_list_unchanged(self):
        """A positive OR-list stays a non-negated OR-branch of positive leaves."""
        oqo = parse_url_to_oqo("works", filter_string="type:article|book")
        branch = oqo.filter_rows[0]
        assert branch.join == "or"
        assert branch.is_negated is False
        assert [leaf.value for leaf in branch.filters] == ["article", "book"]

    def test_sample_parsing(self):
        """Test parsing sample parameter."""
        oqo = parse_url_to_oqo(
            "works",
            filter_string="type:article",
            sample=100
        )
        
        assert oqo.sample == 100
    
    def test_openalex_id_filter(self):
        """Test parsing OpenAlex ID filter."""
        oqo = parse_url_to_oqo(
            "works",
            filter_string="authorships.institutions.lineage:i33213144"
        )
        
        assert oqo.filter_rows[0].column_id == "authorships.institutions.lineage"
        assert oqo.filter_rows[0].value == "i33213144"
    
    def test_search_filter(self):
        """Test parsing search filter."""
        oqo = parse_url_to_oqo(
            "works",
            filter_string="title.search:machine learning"
        )

        assert oqo.filter_rows[0].column_id == "title.search"
        assert oqo.filter_rows[0].value == "machine learning"

    def test_group_by_single_dim(self):
        """Test parsing single-dimension group_by (live API form)."""
        oqo = parse_url_to_oqo(
            "works",
            filter_string="is_retracted:true",
            group_by_string="authorships.institutions.lineage",
        )

        assert len(oqo.group_by) == 1
        assert oqo.group_by[0].column_id == "authorships.institutions.lineage"

    def test_group_by_multi_dim(self):
        """Test parsing multi-dimension group_by (spec §8; live API single-dim)."""
        oqo = parse_url_to_oqo(
            "works",
            filter_string="publication_year:1976-",
            group_by_string="primary_topic.id,publication_year",
        )

        assert len(oqo.group_by) == 2
        # Dimension order is meaningful (spec §8) and preserved
        assert oqo.group_by[0].column_id == "primary_topic.id"
        assert oqo.group_by[1].column_id == "publication_year"


class TestURLRenderer:
    """Tests for OQO → URL rendering."""
    
    def test_simple_filter(self):
        """Test rendering a simple filter."""
        oqo = OQO(
            get_rows="works",
            filter_rows=[LeafFilter(column_id="type", value="article")]
        )
        
        result = render_oqo_to_url(oqo)
        
        assert result["filter"] == "type:article"
    
    def test_negation_filter(self):
        """Test rendering negation."""
        oqo = OQO(
            get_rows="works",
            filter_rows=[LeafFilter(column_id="type", value="article", is_negated=True)]
        )

        result = render_oqo_to_url(oqo)

        assert result["filter"] == "type:!article"
    
    def test_range_gte(self):
        """Test rendering >= range."""
        oqo = OQO(
            get_rows="works",
            filter_rows=[LeafFilter(column_id="publication_year", value="2024", operator=">=")]
        )
        
        result = render_oqo_to_url(oqo)
        
        assert result["filter"] == "publication_year:2024-"
    
    def test_range_lte(self):
        """Test rendering <= range."""
        oqo = OQO(
            get_rows="works",
            filter_rows=[LeafFilter(column_id="cited_by_count", value="100", operator="<=")]
        )
        
        result = render_oqo_to_url(oqo)
        
        assert result["filter"] == "cited_by_count:-100"
    
    def test_or_same_field(self):
        """Test rendering OR with same field."""
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
        
        result = render_oqo_to_url(oqo)
        
        assert result["filter"] == "type:article|book"
    
    def test_null_value(self):
        """Test rendering null value."""
        oqo = OQO(
            get_rows="works",
            filter_rows=[LeafFilter(column_id="language", value=None)]
        )
        
        result = render_oqo_to_url(oqo)
        
        assert result["filter"] == "language:null"
    
    def test_not_null_value(self):
        """Test rendering !null value."""
        oqo = OQO(
            get_rows="works",
            filter_rows=[LeafFilter(column_id="language", value=None, is_negated=True)]
        )

        result = render_oqo_to_url(oqo)

        assert result["filter"] == "language:!null"
    
    def test_sort_rendering(self):
        """Test rendering sort."""
        oqo = OQO(
            get_rows="works",
            filter_rows=[],
            sort_by_column="cited_by_count",
            sort_by_order="desc"
        )

        result = render_oqo_to_url(oqo)

        assert result["sort"] == "cited_by_count:desc"

    def test_group_by_rendering_single_dim(self):
        """Test rendering single-dimension group_by."""
        from query_translation.oqo import GroupBy
        oqo = OQO(
            get_rows="works",
            filter_rows=[LeafFilter(column_id="is_retracted", value=True)],
            group_by=[GroupBy(column_id="authorships.institutions.lineage")],
        )

        result = render_oqo_to_url(oqo)

        assert result["group_by"] == "authorships.institutions.lineage"

    def test_group_by_rendering_multi_dim(self):
        """Test rendering multi-dim group_by (dim order preserved per spec §8)."""
        from query_translation.oqo import GroupBy
        oqo = OQO(
            get_rows="works",
            group_by=[
                GroupBy(column_id="primary_topic.id"),
                GroupBy(column_id="publication_year"),
            ],
        )

        result = render_oqo_to_url(oqo)

        assert result["group_by"] == "primary_topic.id,publication_year"
    
    def test_or_different_fields_fails(self):
        """Test that OR across different fields raises error."""
        oqo = OQO(
            get_rows="works",
            filter_rows=[
                BranchFilter(
                    join="or",
                    filters=[
                        LeafFilter(column_id="type", value="article"),
                        LeafFilter(column_id="publication_year", value="2024")
                    ]
                )
            ]
        )
        
        with pytest.raises(URLRenderError):
            render_oqo_to_url(oqo)
    
    def test_nested_boolean_fails(self):
        """Test that nested boolean logic raises error."""
        oqo = OQO(
            get_rows="works",
            filter_rows=[
                BranchFilter(
                    join="or",
                    filters=[
                        LeafFilter(column_id="type", value="article"),
                        BranchFilter(
                            join="and",
                            filters=[
                                LeafFilter(column_id="type", value="book"),
                                LeafFilter(column_id="type", value="chapter")
                            ]
                        )
                    ]
                )
            ]
        )
        
        with pytest.raises(URLRenderError):
            render_oqo_to_url(oqo)


class TestRoundTrip:
    """Tests for URL → OQO → URL round-trip consistency."""
    
    ROUND_TRIP_TESTS = [
        # Boolean filters
        ("works", "is_oa:true", None),
        ("works", "is_retracted:false", None),
        ("works", "has_doi:true", None),
        
        # Range filters
        ("works", "publication_year:2024", None),
        ("works", "publication_year:2020-", None),
        ("works", "cited_by_count:-100", None),
        
        # Select single value
        ("works", "type:article", None),
        ("works", "authorships.institutions.lineage:i33213144", None),
        ("works", "authorships.countries:us", None),
        
        # Select OR (pipe)
        ("works", "type:article|review", None),
        
        # Negation
        ("works", "type:!article", None),
        
        # Null values
        ("works", "language:null", None),
        ("works", "language:!null", None),
        
        # With sort
        ("works", "type:article", "cited_by_count:desc"),
        
        # Other entities
        ("authors", "last_known_institutions.id:i33213144", None),
    ]
    
    @pytest.mark.parametrize("entity,filter_str,sort_str", ROUND_TRIP_TESTS)
    def test_round_trip(self, entity, filter_str, sort_str):
        """Test that URL → OQO → URL produces consistent results."""
        # Parse URL to OQO
        oqo = parse_url_to_oqo(entity, filter_string=filter_str, sort_string=sort_str)
        
        # Render OQO back to URL
        result = render_oqo_to_url(oqo)
        
        # Parse again
        oqo2 = parse_url_to_oqo(
            entity, 
            filter_string=result["filter"], 
            sort_string=result["sort"]
        )
        
        # Should produce equivalent OQO
        assert oqo.get_rows == oqo2.get_rows
        assert oqo.sort_by_column == oqo2.sort_by_column
        assert oqo.sort_by_order == oqo2.sort_by_order


class TestOQOModel:
    """Tests for OQO data model."""
    
    def test_leaf_filter_to_dict(self):
        """Test LeafFilter serialization."""
        f = LeafFilter(column_id="type", value="article", operator="is")
        d = f.to_dict()
        
        assert d == {"column_id": "type", "value": "article"}
    
    def test_leaf_filter_to_dict_with_operator(self):
        """Test LeafFilter serialization with non-default operator."""
        f = LeafFilter(column_id="title.search", value="ml", operator="contains")
        d = f.to_dict()

        assert d == {"column_id": "title.search", "value": "ml", "operator": "contains"}

    def test_leaf_filter_to_dict_with_is_negated(self):
        """Test LeafFilter serialization carries is_negated polarity bit."""
        f = LeafFilter(column_id="type", value="article", is_negated=True)
        d = f.to_dict()

        # Operator is still the affirmative "is" (default, omitted); is_negated
        # is the polarity bit. New spec: one negation mechanism.
        assert d == {"column_id": "type", "value": "article", "is_negated": True}

    def test_leaf_filter_from_dict(self):
        """Test LeafFilter deserialization round-trips is_negated."""
        d = {"column_id": "type", "value": "article", "is_negated": True}
        f = LeafFilter.from_dict(d)

        assert f.column_id == "type"
        assert f.value == "article"
        assert f.operator == "is"
        assert f.is_negated is True
    
    def test_branch_filter_to_dict(self):
        """Test BranchFilter serialization."""
        f = BranchFilter(
            join="or",
            filters=[
                LeafFilter(column_id="type", value="article"),
                LeafFilter(column_id="type", value="book")
            ]
        )
        d = f.to_dict()
        
        assert d["join"] == "or"
        assert len(d["filters"]) == 2
    
    def test_oqo_to_dict(self):
        """Test OQO serialization."""
        oqo = OQO(
            get_rows="works",
            filter_rows=[LeafFilter(column_id="type", value="article")],
            sort_by_column="cited_by_count",
            sort_by_order="desc"
        )
        d = oqo.to_dict()
        
        assert d["get_rows"] == "works"
        assert len(d["filter_rows"]) == 1
        assert d["sort_by_column"] == "cited_by_count"
        assert d["sort_by_order"] == "desc"
    
    def test_oqo_from_dict(self):
        """Test OQO deserialization."""
        d = {
            "get_rows": "works",
            "filter_rows": [
                {"column_id": "type", "value": "article"},
                {
                    "join": "or",
                    "filters": [
                        {"column_id": "publication_year", "value": "2023"},
                        {"column_id": "publication_year", "value": "2024"}
                    ]
                }
            ],
            "sort_by_column": "cited_by_count",
            "sort_by_order": "desc"
        }
        oqo = OQO.from_dict(d)
        
        assert oqo.get_rows == "works"
        assert len(oqo.filter_rows) == 2
        assert isinstance(oqo.filter_rows[0], LeafFilter)
        assert isinstance(oqo.filter_rows[1], BranchFilter)


class TestValidator:
    """Tests for OQO validation."""
    
    def test_valid_simple_oqo(self):
        """Test validation of a simple valid OQO."""
        oqo = OQO(
            get_rows="works",
            filter_rows=[LeafFilter(column_id="type", value="article")]
        )
        
        result = validate_oqo(oqo)
        
        assert result.valid
        assert len(result.errors) == 0
    
    def test_invalid_entity_type(self):
        """Test validation rejects invalid entity type."""
        oqo = OQO(
            get_rows="widgets",
            filter_rows=[]
        )
        
        result = validate_oqo(oqo)
        
        assert not result.valid
        assert any(e.type == "invalid_entity" for e in result.errors)
    
    def test_invalid_operator(self):
        """Test validation rejects invalid operator."""
        oqo = OQO(
            get_rows="works",
            filter_rows=[LeafFilter(column_id="type", value="article", operator="equals")]
        )
        
        result = validate_oqo(oqo)
        
        assert not result.valid
        assert any(e.type == "invalid_operator" for e in result.errors)
    
    def test_invalid_sort_order(self):
        """Test validation rejects invalid sort order."""
        oqo = OQO(
            get_rows="works",
            filter_rows=[],
            sort_by_column="cited_by_count",
            sort_by_order="ascending"
        )

        result = validate_oqo(oqo)

        assert not result.valid
        assert any(e.type == "invalid_sort_order" for e in result.errors)

    def test_group_by_sort_count_is_valid(self):
        """`count`/`key` are valid sort columns WHEN a group_by is present — they
        order the buckets (legacy core/sort.py special-cases them). Without this
        `?group_by=type&sort=count:desc` 400s `invalid_column` (oxjob #323 G1)."""
        for key in ("count", "key"):
            oqo = parse_url_to_oqo(
                "works", group_by_string="type", sort_string=f"{key}:desc"
            )
            assert oqo.sort_by_column == key
            result = validate_oqo(oqo)
            assert result.valid, (key, [e.type for e in result.errors])

    def test_count_sort_without_group_by_is_invalid(self):
        """`count`/`key` are bucket-ordering keys: invalid as a row sort with no
        group_by (they aren't entity columns)."""
        oqo = OQO(
            get_rows="works",
            filter_rows=[],
            sort_by_column="count",
            sort_by_order="desc",
        )
        result = validate_oqo(oqo)
        assert not result.valid
        assert any(e.type == "invalid_column" for e in result.errors)
    
    def test_invalid_sample(self):
        """Test validation rejects invalid sample."""
        oqo = OQO(
            get_rows="works",
            filter_rows=[],
            sample=-1
        )
        
        result = validate_oqo(oqo)
        
        assert not result.valid
        assert any(e.type == "invalid_sample" for e in result.errors)
    
    def test_empty_branch_filter(self):
        """Test validation rejects empty branch filter."""
        oqo = OQO(
            get_rows="works",
            filter_rows=[BranchFilter(join="or", filters=[])]
        )
        
        result = validate_oqo(oqo)
        
        assert not result.valid
        assert any(e.type == "empty_branch" for e in result.errors)


class TestEquivalence:
    """Three-way equivalence tests."""
    
    EQUIVALENCE_TESTS = [
        {
            "description": "Simple type filter",
            "url": {"filter": "type:article"},
            "oqo": {
                "get_rows": "works",
                "filter_rows": [{"column_id": "type", "value": "article"}]
            }
        },
        {
            "description": "Year range with sort",
            "url": {"filter": "publication_year:2024-", "sort": "fwci:desc"},
            "oqo": {
                "get_rows": "works",
                "filter_rows": [{"column_id": "publication_year", "value": "2024", "operator": ">="}],
                "sort_by_column": "fwci",
                "sort_by_order": "desc"
            }
        },
        {
            "description": "OR within same field",
            "url": {"filter": "type:article|book"},
            "oqo": {
                "get_rows": "works",
                "filter_rows": [{
                    "join": "or",
                    "filters": [
                        {"column_id": "type", "value": "article"},
                        {"column_id": "type", "value": "book"}
                    ]
                }]
            }
        },
    ]
    
    @pytest.mark.parametrize("test_case", EQUIVALENCE_TESTS, ids=lambda x: x["description"])
    def test_equivalence(self, test_case):
        """Test that URL and OQO formats produce equivalent results."""
        url_data = test_case["url"]
        oqo_data = test_case["oqo"]
        
        # Parse URL to OQO
        oqo_from_url = parse_url_to_oqo(
            "works",
            filter_string=url_data.get("filter"),
            sort_string=url_data.get("sort")
        )
        
        # Parse OQO dict
        oqo_from_dict = OQO.from_dict(oqo_data)
        
        # Compare key properties
        assert oqo_from_url.get_rows == oqo_from_dict.get_rows
        assert oqo_from_url.sort_by_column == oqo_from_dict.sort_by_column
        assert oqo_from_url.sort_by_order == oqo_from_dict.sort_by_order

        # Compare filter count
        assert len(oqo_from_url.filter_rows) == len(oqo_from_dict.filter_rows)


class TestTopLevelSearch:
    """`?search=X` → a `default.search` filter (#323 2a).

    Legacy maps a bare `?search=X` to scope `("default", None)`, identical to
    `filter=default.search:X` (core/params.py:96-98). The OQO parser AND's a
    `default.search` contains-filter in.
    """

    def test_search_maps_to_default_search_filter(self):
        oqo = parse_url_to_oqo("works", search_string="quantum computing")
        assert len(oqo.filter_rows) == 1
        leaf = oqo.filter_rows[0]
        assert leaf.column_id == "default.search"
        assert leaf.value == "quantum computing"
        assert leaf.operator == "contains"
        assert validate_oqo(oqo).valid

    def test_search_with_comma_is_one_clause(self):
        """Free-text search containing a comma must NOT be split (it is routed
        through parse_single_filter, not the comma-splitting filter parser)."""
        oqo = parse_url_to_oqo("works", search_string="climate, society")
        assert len(oqo.filter_rows) == 1
        assert oqo.filter_rows[0].value == "climate, society"

    def test_search_anded_with_existing_filter(self):
        oqo = parse_url_to_oqo(
            "works", filter_string="type:article", search_string="quantum"
        )
        cols = [f.column_id for f in oqo.filter_rows]
        assert "type" in cols and "default.search" in cols
        assert validate_oqo(oqo).valid

    def test_search_lucene_boolean_lifts(self):
        """A Lucene boolean in the search value lifts to AND'd contains leaves,
        same as `filter=default.search:a AND b`."""
        oqo = parse_url_to_oqo("works", search_string="machine AND learning")
        assert len(oqo.filter_rows) == 2
        assert all(f.column_id == "default.search" for f in oqo.filter_rows)
        assert {f.value for f in oqo.filter_rows} == {"machine", "learning"}


class TestRelevanceScoreSort:
    """`relevance_score` is a sortable synthetic column (#323 2b).

    Sortable but NOT filterable (legacy core/sort.py maps it to ES _score).
    Gated on a search clause being present; descending only.
    """

    def test_relevance_with_search_is_valid(self):
        oqo = parse_url_to_oqo(
            "works", search_string="quantum", sort_string="relevance_score:desc"
        )
        assert validate_oqo(oqo).valid

    def test_relevance_with_search_filter_is_valid(self):
        """A `*.search` filter (not just `?search=`) also satisfies the gate."""
        oqo = parse_url_to_oqo(
            "works",
            filter_string="display_name.search:quantum",
            sort_string="relevance_score:desc",
        )
        assert validate_oqo(oqo).valid

    def test_relevance_without_search_is_rejected(self):
        oqo = parse_url_to_oqo("works", sort_string="relevance_score:desc")
        result = validate_oqo(oqo)
        assert not result.valid
        assert any(
            e.type == "relevance_sort_requires_search" for e in result.errors
        )

    def test_relevance_ascending_is_rejected(self):
        oqo = parse_url_to_oqo(
            "works", search_string="quantum", sort_string="relevance_score:asc"
        )
        result = validate_oqo(oqo)
        assert not result.valid
        assert any(e.type == "invalid_sort_order" for e in result.errors)

    def test_relevance_score_is_not_filterable(self):
        """It is sort-only — using it as a filter column stays invalid."""
        oqo = parse_url_to_oqo("works", filter_string="relevance_score:5")
        assert not validate_oqo(oqo).valid


class TestSearchAwareSortInExecutor:
    """The OQO executor delegates sort to legacy `apply_sorting`, signalling a
    search clause via params["search"] (#323 2c). With a search clause present:
    - no explicit sort ⇒ works default `_score, publication_date, id` (order parity)
    - relevance_score:desc ⇒ ES `_score`
    Without a search clause, the non-search default sort applies.
    """

    def _sort_for(self, **kw):
        from flask import Flask, request
        from elasticsearch_dsl import Search
        from query_translation.views import _build_params_from_oqo
        from core.shared_view import apply_sorting

        oqo = parse_url_to_oqo(entity_type="works", **kw)
        app = Flask(__name__)
        with app.test_request_context("/"):
            params = _build_params_from_oqo(oqo, request)
        s = Search(index="works-v1")
        s = apply_sorting(params, {}, ["-publication_date", "id"], "works-v1", s)
        return s.to_dict().get("sort"), params["search"]

    def test_search_no_sort_uses_works_relevance_default(self):
        sort, search = self._sort_for(search_string="quantum")
        assert search  # search clause signalled
        assert sort == ["_score", "publication_date", "id"]

    def test_no_search_no_sort_uses_default(self):
        sort, search = self._sort_for()
        assert search is None
        assert sort == [{"publication_date": {"order": "desc"}}, "id"]

    def test_search_relevance_sort_maps_to_score(self):
        sort, search = self._sort_for(
            search_string="quantum", sort_string="relevance_score:desc"
        )
        assert sort == ["_score"]

    def test_search_clause_from_filter_also_signals(self):
        sort, search = self._sort_for(filter_string="display_name.search:quantum")
        assert search
        assert sort == ["_score", "publication_date", "id"]
