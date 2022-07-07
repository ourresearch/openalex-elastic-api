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
