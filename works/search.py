from elasticsearch_dsl import A, Q
from elasticsearch_dsl.aggs import Nested, Terms


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
