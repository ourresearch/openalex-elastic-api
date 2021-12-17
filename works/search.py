from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from elasticsearch_dsl import A, Q
from elasticsearch_dsl.aggs import Nested, Terms

from works.exceptions import APIQueryParamsError


@dataclass(frozen=True)
class Filter:
    param: str
    custom_es_field: Optional[str] = None
    is_bool_query: bool = False
    is_date_query: bool = False
    is_range_query: bool = False

    def es_field(self) -> str:
        if self.custom_es_field:
            field = self.custom_es_field
        elif "." in self.param:
            field = self.param.replace(".", "__")
        else:
            field = self.param
        return field


filters = [
    Filter(param="publication_year", is_range_query=True),
    Filter(param="publication_date", is_date_query=True),
    Filter(param="venue.issn"),
    Filter(param="venue.publisher"),
    Filter(param="genre"),
    Filter(param="is_paratext", is_bool_query=True),
    Filter(param="oa_status"),
    Filter(param="is_oa", is_bool_query=True),
    Filter(param="author.id", custom_es_field="authorships__author__id"),
    Filter(param="author.orcid", custom_es_field="authorships__author__orcid"),
    Filter(param="institutions.id", custom_es_field="authorships__institutions__id"),
    Filter(param="institutions.ror", custom_es_field="authorships__institutions__ror"),
    Filter(
        param="institutions.country_code",
        custom_es_field="authorships__institutions__country_code",
    ),
    Filter(
        param="institutions.type", custom_es_field="authorships__institutions__type"
    ),
    Filter(param="cited_by_count", is_range_query=True),
    Filter(param="is_retracted", is_bool_query=True),
    Filter(param="concepts.id"),
    Filter(param="concepts.wikidata"),
    Filter(param="alternate_locations.license"),
    Filter(param="alternate_locations.version"),
    Filter(param="alternate_locations.venue_id"),
    Filter(param="referenced_works"),
]


def filter_records(filter_params, s):
    for filter in filters:

        # range query
        if filter.param in filter_params and filter.is_range_query:
            param = filter_params[filter.param]
            if "<" in param:
                param = param[1:]
                validate_range_param(filter, param)
                kwargs = {filter.es_field(): {"lte": int(param)}}
                s = s.filter("range", **kwargs)
            elif ">" in param:
                param = param[1:]
                validate_range_param(filter, param)
                kwargs = {filter.es_field(): {"gt": int(param)}}
                s = s.filter("range", **kwargs)
            elif param == "null":
                s = s.exclude("exists", field=filter.es_field())
            else:
                validate_range_param(filter, param)
                kwargs = {filter.es_field(): param}
                s = s.filter("term", **kwargs)

        # date query
        elif filter.param in filter_params and filter.is_date_query:
            param = filter_params[filter.param]
            if "<" in param:
                param = param[1:]
                validate_date_param(filter, param)
                kwargs = {filter.es_field(): {"lte": param}}
                s = s.filter("range", **kwargs)
            elif ">" in param:
                param = param[1:]
                validate_date_param(filter, param)
                kwargs = {filter.es_field(): {"gt": param}}
                s = s.filter("range", **kwargs)
            elif param == "null":
                s = s.exclude("exists", field=filter.es_field())
            else:
                validate_date_param(filter, param)
                kwargs = {filter.es_field(): param}
                s = s.filter("term", **kwargs)

        # boolean query
        elif filter.param in filter_params and filter.is_bool_query:
            param = filter_params[filter.param]
            param = param.lower()
            if param == "null":
                s = s.exclude("exists", field=filter.es_field())
            else:
                kwargs = {filter.es_field(): param}
                s = s.filter("term", **kwargs)

        # regular query
        elif filter.param in filter_params:
            param = filter_params[filter.param]
            if param == "null":
                field = filter.es_field()
                field = field.replace("__", ".")
                s = s.exclude("exists", field=field)
            elif "country_code" in filter.param:
                param = param.upper()
                kwargs = {filter.es_field(): param}
                s = s.filter("term", **kwargs)
            else:
                param = param.lower().split(" ")
                kwargs = {filter.es_field(): param}
                s = s.filter("terms", **kwargs)
    return s


def validate_range_param(filter, param):
    try:
        param = int(param)
    except ValueError:
        raise APIQueryParamsError(f"Value for param {filter.param} must be a number.")


def validate_date_param(filter, param):
    try:
        date = datetime.strptime(param, "%Y-%m-%d")
    except ValueError:
        raise APIQueryParamsError(
            f"Value for param {filter.param} must be a date in format 2020-05-17."
        )


def search_records(search, s):
    if search:
        q = (
            # Q("match", work_title={"query": search_params["title"]})
            Q(
                "match",
                display_name={
                    "query": search,
                    "operator": "and",
                },
            )
            | Q(
                "match_phrase",
                display_name={"query": search, "boost": 2},
            )
        )
        s = s.query(q)
        # alternate method
        # s = s.query(
        #     "match_phrase", work_title={"query": search_params["title"], "slop": 1}
        # )
    return s


def group_by_records(group_by, s, group_by_size, query_type):
    if group_by and group_by == "author_id" and query_type != "author_id_by_year":
        a = A("terms", field="author_ids", size=group_by_size)
        s.aggs.bucket("groupby", a)

    if group_by and group_by == "country":
        s.aggs.bucket("affiliations", Nested(path="affiliations")).bucket(
            "groupby", Terms(field="affiliations.country")
        )

    if group_by and group_by == "issn" and query_type != "issns_by_year":
        a = A("terms", field="journal.all_issns", size=group_by_size)
        s.aggs.bucket("groupby", a)

    if group_by and group_by == "open_access":
        a = A(
            "terms",
            field="unpaywall.is_oa_bool",
            order={"_term": "desc"},
            size=group_by_size,
        )
        s.aggs.bucket("groupby", a)

    if group_by and group_by == "year":
        a = A("terms", field="year", order={"_term": "desc"}, size=group_by_size)
        s.aggs.bucket("groupby", a)

    return s
