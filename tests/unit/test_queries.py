from elasticsearch_dsl import Search

from core.filter import filter_records
from core.search import search_records_full, search_records_phrase
from core.sort import sort_records
from core.utils import map_filter_params, map_sort_params
from works.fields import fields_dict


def test_search_full(client):
    s = Search()
    search = "covid-19"
    q = search_records_full(search)
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
    search = "covid-19"
    q = search_records_phrase(search)
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
                "query": {"match_phrase": {"display_name": {"query": "covid-19"}}},
                "boost_mode": "multiply",
            }
        }
    }


def test_search_with_display_name_sort(client):
    s = Search()
    search = "covid-19"
    sort_args = "display_name"
    sort_params = map_sort_params(sort_args)
    q = search_records_full(search)
    s = s.query(q)
    s = sort_records(fields_dict, None, sort_params, s)
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
        "sort": ["display_name.keyword"],
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
    filter_args = "host_venue.issn:2333-3334,host_venue.publisher:null"
    filter_params = map_filter_params(filter_args)
    s = filter_records(fields_dict, filter_params, s)
    assert s.to_dict() == {
        "query": {
            "bool": {
                "must": [
                    {"term": {"host_venue.issn.lower": "2333-3334"}},
                    {
                        "bool": {
                            "must_not": [
                                {"exists": {"field": "host_venue.publisher.lower"}}
                            ]
                        }
                    },
                ]
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
    s = sort_records(fields_dict, None, sort_params, s)

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