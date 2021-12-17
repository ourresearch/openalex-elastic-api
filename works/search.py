from dataclasses import dataclass
from typing import Optional

from elasticsearch_dsl import A, Q
from elasticsearch_dsl.aggs import Nested, Terms


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
    Filter(param="is_para_text", is_bool_query=True),
]


def filter_records(filter_params, s):
    for filter in filters:
        if filter_params and filter.param in filter_params:
            kwargs = {filter.es_field(): filter_params[filter.param]}
            s = s.filter("term", **kwargs)

    # if filter_params and "id" in filter_params:
    #     s = s.filter("term", paper_id=filter_params["id"])
    # if filter_params and "author_id" in filter_params:
    #     s = s.filter("term", author_ids=filter_params["author_id"])
    # if filter_params and "issn" in filter_params:
    #     s = s.filter("term", journal__all_issns=filter_params["issn"])
    # if filter_params and "ror" in filter_params:
    #     s = s.filter(
    #         "nested",
    #         path="affiliations",
    #         query=Q("term", affiliations__ror=filter_params["ror_id"]),
    #     )
    # if filter_params and "publication_year" in filter_params:
    #     publication_year = filter_params["publication_year"]
    #     if "<" in publication_year:
    #         publication_year = publication_year[1:]
    #         s = s.filter("range", publication_year={"lte": int(publication_year)})
    #     if ">" in publication_year:
    #         publication_year = publication_year[1:]
    #         s = s.filter("range", publication_year={"gt": int(publication_year)})
    #     else:
    #         s = s.filter("term", publication_year=int(publication_year))
    return s


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
