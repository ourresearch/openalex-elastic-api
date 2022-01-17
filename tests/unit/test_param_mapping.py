from core.utils import map_filter_params, map_sort_params


class TestFilterParamMapping:
    def test_basic_filter_mapping(self, client):
        filter_params = "publication_year:2020,display_name.search:covid-19 deaths,cited_by_count:>200"
        parsed_params = map_filter_params(filter_params)
        assert parsed_params == {
            "publication_year": "2020",
            "display_name.search": "covid-19 deaths",
            "cited_by_count": ">200",
        }

    def test_filter_mapping_with_url(self, client):
        filter_params = "publication_year:2020,display_name.search:covid-19 deaths,author.id:https://openalex.org/C234343"
        parsed_params = map_filter_params(filter_params)
        assert parsed_params == {
            "publication_year": "2020",
            "display_name.search": "covid-19 deaths",
            "author.id": "https://openalex.org/C234343",
        }

    def test_filter_mapping_with_hyphens(self, client):
        filter_params = "publication-year:2020,display-name.search:covid-19 deaths,author.id:https://openalex.org/C234343,cited-by_count:>200"
        parsed_params = map_filter_params(filter_params)
        assert parsed_params == {
            "publication_year": "2020",
            "display_name.search": "covid-19 deaths",
            "author.id": "https://openalex.org/C234343",
            "cited_by_count": ">200",
        }

    def test_filter_mapping_with_search_quotes(self, client):
        filter_params = 'publication-year:2020,title.search:"covid-19 deaths"'
        parsed_params = map_filter_params(filter_params)
        assert parsed_params == {
            "publication_year": "2020",
            "title.search": '"covid-19 deaths"',
        }

    def test_filter_mapping_with_multiple_colons(self, client):
        filter_params = "publication-year:2020,title.search:book 1: how to win friends"
        parsed_params = map_filter_params(filter_params)
        assert parsed_params == {
            "publication_year": "2020",
            "title.search": "book 1: how to win friends",
        }


class TestSortParamMapping:
    def test_sort_mapping_basic(self, client):
        sort_params = "publication_year:desc,cited_by_count"
        parsed_params = map_sort_params(sort_params)
        assert parsed_params == {"publication_year": "desc", "cited_by_count": "asc"}

    def test_sort_mapping_hyphen(self, client):
        sort_params = "publication-year:desc,cited-by-count"
        parsed_params = map_sort_params(sort_params)
        assert parsed_params == {"publication_year": "desc", "cited_by_count": "asc"}
