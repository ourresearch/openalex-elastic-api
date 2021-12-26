from elasticsearch_dsl import Search

from core.filter import filter_records
from core.sort import sort_records
from core.utils import map_filter_params, map_sort_params
from works.fields import fields_dict


def test_index(client):
    res = client.get("/")
    assert res.status_code == 200


def test_filter_query(client):
    s = Search()
    filter_args = "venue.publisher:wiley,publication_year:>2015"
    filter_params = map_filter_params(filter_args)
    s = filter_records(fields_dict, filter_params, s)
    assert s.to_dict() == {
        "query": {
            "bool": {
                "filter": [
                    {"terms": {"venue.publisher": ["wiley"]}},
                    {"range": {"publication_year": {"gt": 2015}}},
                ]
            }
        }
    }


def test_sort_query(client):
    s = Search()
    filter_args = "venue.publisher:wiley,publication_year:>2015"
    sort_args = "publication_date,cited_by_count:asc,venue.publisher:desc"
    filter_params = map_filter_params(filter_args)
    sort_params = map_sort_params(sort_args)

    s = filter_records(fields_dict, filter_params, s)

    # sort
    s = sort_records(fields_dict, sort_params, s)

    assert s.to_dict() == {
        "query": {
            "bool": {
                "filter": [
                    {"terms": {"venue.publisher": ["wiley"]}},
                    {"range": {"publication_year": {"gt": 2015}}},
                ]
            }
        },
        "sort": [
            "publication_date",
            "cited_by_count",
            {"venue.publisher.keyword": {"order": "desc"}},
        ],
    }
