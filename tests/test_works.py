from elasticsearch_dsl import Search

from core.filter import filter_records
from core.utils import map_query_params
from works.fields import fields_dict


def test_index(client):
    res = client.get("/")
    assert res.status_code == 200


def test_filter_query(client):
    s = Search()
    filter_args = "venue.publisher:wiley,publication_year:>2015"
    filter_params = map_query_params(filter_args)
    for key, value in filter_params.items():
        field = fields_dict[key]
        field.value = value
        field.validate()
        s = filter_records(field, s)
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
