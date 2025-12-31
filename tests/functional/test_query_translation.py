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
        assert len(oqo.filter_works) == 1
        assert oqo.filter_works[0].column_id == "type"
        assert oqo.filter_works[0].value == "article"
        assert oqo.filter_works[0].operator == "is"
    
    def test_multiple_filters(self):
        """Test parsing multiple filters (AND)."""
        oqo = parse_url_to_oqo(
            "works", 
            filter_string="type:article,publication_year:2024"
        )
        
        assert len(oqo.filter_works) == 2
    
    def test_or_filter(self):
        """Test parsing OR filter with pipe."""
        oqo = parse_url_to_oqo("works", filter_string="type:article|book")
        
        assert len(oqo.filter_works) == 1
        branch = oqo.filter_works[0]
        assert isinstance(branch, BranchFilter)
        assert branch.join == "or"
        assert len(branch.filters) == 2
    
    def test_negation_filter(self):
        """Test parsing negation with !."""
        oqo = parse_url_to_oqo("works", filter_string="type:!article")
        
        assert oqo.filter_works[0].operator == "is not"
        assert oqo.filter_works[0].value == "article"
    
    def test_range_gte(self):
        """Test parsing >= range (trailing dash)."""
        oqo = parse_url_to_oqo("works", filter_string="publication_year:2024-")
        
        assert oqo.filter_works[0].operator == ">="
        assert oqo.filter_works[0].value == "2024"
    
    def test_range_lte(self):
        """Test parsing <= range (leading dash)."""
        oqo = parse_url_to_oqo("works", filter_string="cited_by_count:-100")
        
        assert oqo.filter_works[0].operator == "<="
        assert oqo.filter_works[0].value == "100"
    
    def test_range_both(self):
        """Test parsing bounded range."""
        oqo = parse_url_to_oqo("works", filter_string="publication_year:2020-2024")
        
        # Should create two filters: >= 2020 AND <= 2024
        assert len(oqo.filter_works) == 2
        operators = {f.operator for f in oqo.filter_works}
        assert operators == {">=", "<="}
    
    def test_null_value(self):
        """Test parsing null value."""
        oqo = parse_url_to_oqo("works", filter_string="language:null")
        
        assert oqo.filter_works[0].value is None
        assert oqo.filter_works[0].operator == "is"
    
    def test_not_null_value(self):
        """Test parsing !null value."""
        oqo = parse_url_to_oqo("works", filter_string="language:!null")
        
        assert oqo.filter_works[0].value is None
        assert oqo.filter_works[0].operator == "is not"
    
    def test_boolean_value(self):
        """Test parsing boolean value."""
        oqo = parse_url_to_oqo("works", filter_string="is_oa:true")
        
        assert oqo.filter_works[0].value == "true"
    
    def test_sort_parsing(self):
        """Test parsing sort parameter."""
        oqo = parse_url_to_oqo(
            "works",
            filter_string="type:article",
            sort_string="cited_by_count:desc"
        )
        
        assert oqo.sort_by_column == "cited_by_count"
        assert oqo.sort_by_order == "desc"
    
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
        
        assert oqo.filter_works[0].column_id == "authorships.institutions.lineage"
        assert oqo.filter_works[0].value == "i33213144"
    
    def test_search_filter(self):
        """Test parsing search filter."""
        oqo = parse_url_to_oqo(
            "works",
            filter_string="title.search:machine learning"
        )
        
        assert oqo.filter_works[0].column_id == "title.search"
        assert oqo.filter_works[0].value == "machine learning"


class TestURLRenderer:
    """Tests for OQO → URL rendering."""
    
    def test_simple_filter(self):
        """Test rendering a simple filter."""
        oqo = OQO(
            get_rows="works",
            filter_works=[LeafFilter(column_id="type", value="article")]
        )
        
        result = render_oqo_to_url(oqo)
        
        assert result["filter"] == "type:article"
    
    def test_negation_filter(self):
        """Test rendering negation."""
        oqo = OQO(
            get_rows="works",
            filter_works=[LeafFilter(column_id="type", value="article", operator="is not")]
        )
        
        result = render_oqo_to_url(oqo)
        
        assert result["filter"] == "type:!article"
    
    def test_range_gte(self):
        """Test rendering >= range."""
        oqo = OQO(
            get_rows="works",
            filter_works=[LeafFilter(column_id="publication_year", value="2024", operator=">=")]
        )
        
        result = render_oqo_to_url(oqo)
        
        assert result["filter"] == "publication_year:2024-"
    
    def test_range_lte(self):
        """Test rendering <= range."""
        oqo = OQO(
            get_rows="works",
            filter_works=[LeafFilter(column_id="cited_by_count", value="100", operator="<=")]
        )
        
        result = render_oqo_to_url(oqo)
        
        assert result["filter"] == "cited_by_count:-100"
    
    def test_or_same_field(self):
        """Test rendering OR with same field."""
        oqo = OQO(
            get_rows="works",
            filter_works=[
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
            filter_works=[LeafFilter(column_id="language", value=None)]
        )
        
        result = render_oqo_to_url(oqo)
        
        assert result["filter"] == "language:null"
    
    def test_not_null_value(self):
        """Test rendering !null value."""
        oqo = OQO(
            get_rows="works",
            filter_works=[LeafFilter(column_id="language", value=None, operator="is not")]
        )
        
        result = render_oqo_to_url(oqo)
        
        assert result["filter"] == "language:!null"
    
    def test_sort_rendering(self):
        """Test rendering sort."""
        oqo = OQO(
            get_rows="works",
            filter_works=[],
            sort_by_column="cited_by_count",
            sort_by_order="desc"
        )
        
        result = render_oqo_to_url(oqo)
        
        assert result["sort"] == "cited_by_count:desc"
    
    def test_or_different_fields_fails(self):
        """Test that OR across different fields raises error."""
        oqo = OQO(
            get_rows="works",
            filter_works=[
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
            filter_works=[
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
        f = LeafFilter(column_id="type", value="article", operator="is not")
        d = f.to_dict()
        
        assert d == {"column_id": "type", "value": "article", "operator": "is not"}
    
    def test_leaf_filter_from_dict(self):
        """Test LeafFilter deserialization."""
        d = {"column_id": "type", "value": "article", "operator": "is not"}
        f = LeafFilter.from_dict(d)
        
        assert f.column_id == "type"
        assert f.value == "article"
        assert f.operator == "is not"
    
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
            filter_works=[LeafFilter(column_id="type", value="article")],
            sort_by_column="cited_by_count",
            sort_by_order="desc"
        )
        d = oqo.to_dict()
        
        assert d["get_rows"] == "works"
        assert len(d["filter_works"]) == 1
        assert d["sort_by_column"] == "cited_by_count"
        assert d["sort_by_order"] == "desc"
    
    def test_oqo_from_dict(self):
        """Test OQO deserialization."""
        d = {
            "get_rows": "works",
            "filter_works": [
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
        assert len(oqo.filter_works) == 2
        assert isinstance(oqo.filter_works[0], LeafFilter)
        assert isinstance(oqo.filter_works[1], BranchFilter)


class TestValidator:
    """Tests for OQO validation."""
    
    def test_valid_simple_oqo(self):
        """Test validation of a simple valid OQO."""
        oqo = OQO(
            get_rows="works",
            filter_works=[LeafFilter(column_id="type", value="article")]
        )
        
        result = validate_oqo(oqo)
        
        assert result.valid
        assert len(result.errors) == 0
    
    def test_invalid_entity_type(self):
        """Test validation rejects invalid entity type."""
        oqo = OQO(
            get_rows="widgets",
            filter_works=[]
        )
        
        result = validate_oqo(oqo)
        
        assert not result.valid
        assert any(e.type == "invalid_entity" for e in result.errors)
    
    def test_invalid_operator(self):
        """Test validation rejects invalid operator."""
        oqo = OQO(
            get_rows="works",
            filter_works=[LeafFilter(column_id="type", value="article", operator="equals")]
        )
        
        result = validate_oqo(oqo)
        
        assert not result.valid
        assert any(e.type == "invalid_operator" for e in result.errors)
    
    def test_invalid_sort_order(self):
        """Test validation rejects invalid sort order."""
        oqo = OQO(
            get_rows="works",
            filter_works=[],
            sort_by_column="cited_by_count",
            sort_by_order="ascending"
        )
        
        result = validate_oqo(oqo)
        
        assert not result.valid
        assert any(e.type == "invalid_sort_order" for e in result.errors)
    
    def test_invalid_sample(self):
        """Test validation rejects invalid sample."""
        oqo = OQO(
            get_rows="works",
            filter_works=[],
            sample=-1
        )
        
        result = validate_oqo(oqo)
        
        assert not result.valid
        assert any(e.type == "invalid_sample" for e in result.errors)
    
    def test_empty_branch_filter(self):
        """Test validation rejects empty branch filter."""
        oqo = OQO(
            get_rows="works",
            filter_works=[BranchFilter(join="or", filters=[])]
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
                "filter_works": [{"column_id": "type", "value": "article"}]
            }
        },
        {
            "description": "Year range with sort",
            "url": {"filter": "publication_year:2024-", "sort": "fwci:desc"},
            "oqo": {
                "get_rows": "works",
                "filter_works": [{"column_id": "publication_year", "value": "2024", "operator": ">="}],
                "sort_by_column": "fwci",
                "sort_by_order": "desc"
            }
        },
        {
            "description": "OR within same field",
            "url": {"filter": "type:article|book"},
            "oqo": {
                "get_rows": "works",
                "filter_works": [{
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
        assert len(oqo_from_url.filter_works) == len(oqo_from_dict.filter_works)
