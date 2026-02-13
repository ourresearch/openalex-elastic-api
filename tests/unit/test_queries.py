import pytest
from elasticsearch_dsl import Search

from core.filter import filter_records
from core.search import SearchOpenAlex
from core.sort import get_sort_fields
from core.utils import map_filter_params, map_sort_params
from works.fields import fields_dict


def test_search_full(client):
    s = Search()
    search_terms = "covid-19"
    search_oa = SearchOpenAlex(search_terms=search_terms)
    q = search_oa.build_query()
    s = s.query(q)
    assert s.to_dict() == {
        "query": {
            "function_score": {
                "functions": [
                    {
                        "field_value_factor": {
                            "field": "cited_by_count",
                            "factor": 1,
                            "modifier": "sqrt",
                            "missing": 1,
                        }
                    }
                ],
                "query": {
                    "bool": {
                        "should": [
                            {
                                "match": {
                                    "display_name": {
                                        "query": "covid-19",
                                        "operator": "and",
                                    }
                                }
                            },
                            {
                                "match_phrase": {
                                    "display_name": {"query": "covid-19", "boost": 2}
                                }
                            },
                        ]
                    }
                },
                "boost_mode": "multiply",
            }
        }
    }


def test_search_phrase(client):
    s = Search()
    search_terms = '"covid-19"'
    search_oa = SearchOpenAlex(search_terms=search_terms)
    q = search_oa.build_query()
    s = s.query(q)
    assert s.to_dict() == {
        "query": {
            "function_score": {
                "functions": [
                    {
                        "field_value_factor": {
                            "field": "cited_by_count",
                            "factor": 1,
                            "modifier": "sqrt",
                            "missing": 1,
                        }
                    }
                ],
                "query": {"match_phrase": {"display_name": {"query": '"covid-19"'}}},
                "boost_mode": "multiply",
            }
        }
    }


def test_search_with_display_name_sort(client):
    s = Search()
    search_terms = "covid-19"
    sort_args = "display_name"
    sort_params = map_sort_params(sort_args)
    search_oa = SearchOpenAlex(search_terms=search_terms)
    q = search_oa.build_query()
    s = s.query(q)
    sort_fields = get_sort_fields(fields_dict, None, sort_params)
    s = s.sort(*sort_fields)
    assert s.to_dict() == {
        "query": {
            "function_score": {
                "functions": [
                    {
                        "field_value_factor": {
                            "field": "cited_by_count",
                            "factor": 1,
                            "modifier": "sqrt",
                            "missing": 1,
                        }
                    }
                ],
                "query": {
                    "bool": {
                        "should": [
                            {
                                "match": {
                                    "display_name": {
                                        "query": "covid-19",
                                        "operator": "and",
                                    }
                                }
                            },
                            {
                                "match_phrase": {
                                    "display_name": {"query": "covid-19", "boost": 2}
                                }
                            },
                        ]
                    }
                },
                "boost_mode": "multiply",
            }
        },
        "sort": ["display_name.lower"],
    }


def test_filter_range_query(client):
    s = Search()
    filter_args = "publication_year:>2015,cited_by_count:<10"
    filter_params = map_filter_params(filter_args)
    s = filter_records(fields_dict, filter_params, s)
    assert s.to_dict() == {
        "query": {
            "bool": {
                "must": [
                    {"range": {"publication_year": {"gt": 2015}}},
                    {"range": {"cited_by_count": {"lt": 10}}},
                ]
            }
        }
    }


def test_filter_regular_query(client):
    s = Search()
    filter_args = (
        "host_venue.issn:2333-3334,host_venue.publisher:null,publication_year:2020"
    )
    filter_params = map_filter_params(filter_args)
    s = filter_records(fields_dict, filter_params, s)
    assert s.to_dict() == {
        "query": {
            "bool": {
                "must_not": [{"exists": {"field": "host_venue.publisher.lower"}}],
                "must": [
                    {"term": {"host_venue.issn.lower": "2333-3334"}},
                    {"term": {"publication_year": "2020"}},
                ],
            }
        }
    }


def test_filter_or_query(client):
    s = Search()
    filter_args = "host_venue.issn:2333-3334|5555-7777,publication_year:2020,publication_year:2021"
    filter_params = map_filter_params(filter_args)
    s = filter_records(fields_dict, filter_params, s)
    assert s.to_dict() == {
        "query": {
            "bool": {
                "should": [
                    {"term": {"host_venue.issn.lower": "2333-3334"}},
                    {"term": {"host_venue.issn.lower": "5555-7777"}},
                ],
                "minimum_should_match": 1,
                "must": [
                    {"term": {"publication_year": "2020"}},
                    {"term": {"publication_year": "2021"}},
                ],
            }
        }
    }


def test_sort_query(client):
    s = Search()
    filter_args = "host_venue.publisher:wiley,publication_year:>2015"
    sort_args = "publication_date,cited_by_count:asc,host_venue.publisher:desc"
    filter_params = map_filter_params(filter_args)
    sort_params = map_sort_params(sort_args)

    s = filter_records(fields_dict, filter_params, s)

    # sort
    sort_fields = get_sort_fields(fields_dict, None, sort_params)
    s = s.sort(*sort_fields)

    assert s.to_dict() == {
        "query": {
            "bool": {
                "must": [
                    {"match_phrase": {"host_venue.publisher.lower": "wiley"}},
                    {"range": {"publication_year": {"gt": 2015}}},
                ]
            }
        },
        "sort": [
            "publication_date",
            "cited_by_count",
            {"host_venue.publisher.keyword": {"order": "desc"}},
        ],
    }


# --- Wildcard detection tests ---


class TestHasWildcard:
    @pytest.mark.parametrize(
        "terms",
        [
            "machin*",
            "chem*stry",
            "wom?n",
            "roam~",
            "machine~2",
            '"climate change"~5',
        ],
    )
    def test_has_wildcard_true(self, terms):
        search_oa = SearchOpenAlex(search_terms=terms)
        assert search_oa.has_wildcard() is True

    @pytest.mark.parametrize(
        "terms",
        [
            "machine learning",
            "What is gene therapy?",
            "therapy?",
            "5 * 3",
            "covid-19",
            "hello world",
            "a*",       # too short prefix for *
            "th*",      # too short prefix for *
            "*ab",      # too short suffix for leading *
            "a~2",      # too short prefix for ~
            "go~1",     # too short prefix for ~
        ],
    )
    def test_has_wildcard_false(self, terms):
        search_oa = SearchOpenAlex(search_terms=terms)
        assert search_oa.has_wildcard() is False


class TestWildcardQueryRouting:
    def test_wildcard_produces_query_string(self):
        """Wildcard search terms should route through query_string."""
        search_oa = SearchOpenAlex(search_terms="machin*")
        q = search_oa.primary_match_query()
        q_dict = q.to_dict()
        assert "query_string" in q_dict
        assert q_dict["query_string"]["allow_leading_wildcard"] is False
        assert q_dict["query_string"]["query"] == "machin*"

    def test_wildcard_preserves_asterisk(self):
        """Wildcard characters should NOT be stripped from query."""
        search_oa = SearchOpenAlex(search_terms="machin*")
        q = search_oa.primary_match_query()
        q_dict = q.to_dict()
        assert "*" in q_dict["query_string"]["query"]

    def test_plain_search_produces_match(self):
        """Non-wildcard search should still use match + match_phrase (regression)."""
        search_oa = SearchOpenAlex(search_terms="machine learning")
        q = search_oa.primary_match_query()
        q_dict = q.to_dict()
        assert "bool" in q_dict
        should = q_dict["bool"]["should"]
        query_types = [list(clause.keys())[0] for clause in should]
        assert "match" in query_types
        assert "match_phrase" in query_types

    def test_question_mark_punctuation_uses_match(self):
        """Trailing ? as punctuation should NOT trigger query_string."""
        search_oa = SearchOpenAlex(search_terms="What is gene therapy?")
        q = search_oa.primary_match_query()
        q_dict = q.to_dict()
        assert "bool" in q_dict
        assert "query_string" not in q_dict

    def test_boolean_with_wildcard_preserves_wildcard(self):
        """Boolean search with wildcards should preserve the wildcard chars."""
        search_oa = SearchOpenAlex(search_terms="machin* AND learn*")
        q = search_oa.primary_match_query()
        q_dict = q.to_dict()
        assert "query_string" in q_dict
        assert "machin*" in q_dict["query_string"]["query"]
        assert "learn*" in q_dict["query_string"]["query"]

    def test_wildcard_secondary_field_query_string(self):
        """Wildcard with primary+secondary fields should produce query_string for both."""
        search_oa = SearchOpenAlex(
            search_terms="machin*",
            secondary_field="abstract",
        )
        q = search_oa.primary_secondary_match_query()
        q_dict = q.to_dict()
        should = q_dict["bool"]["should"]
        for clause in should:
            assert "query_string" in clause
            assert clause["query_string"]["allow_leading_wildcard"] is False

    def test_wildcard_tertiary_field_query_string(self):
        """Wildcard with three fields should produce query_string for all three."""
        search_oa = SearchOpenAlex(
            search_terms="machin*",
            secondary_field="abstract",
            tertiary_field="fulltext",
        )
        q = search_oa.primary_secondary_tertiary_match_query()
        q_dict = q.to_dict()
        should = q_dict["bool"]["should"]
        assert len(should) == 3
        for clause in should:
            assert "query_string" in clause
            assert clause["query_string"]["allow_leading_wildcard"] is False
