from elasticsearch_dsl import A, Q
from elasticsearch_dsl.aggs import Nested, Terms


def filter_records(filters, s):
    if filters and "id" in filters:
        s = s.filter("term", paper_id=filters["id"])
    if filters and "author_id" in filters:
        s = s.filter("term", author_ids=filters["author_id"])
    if filters and "issn" in filters:
        s = s.filter("term", journal__all_issns=filters["issn"])
    if filters and "ror_id" in filters:
        s = s.filter(
            "nested",
            path="affiliations",
            query=Q("term", affiliations__ror=filters["ror_id"]),
        )
    if filters and "year" in filters:
        year = filters["year"]
        if "<" in year:
            year = year[1:]
            s = s.filter("range", year={"lte": int(year)})
        if ">" in year:
            year = year[1:]
            s = s.filter("range", year={"gt": int(year)})
        else:
            s = s.filter("term", year=int(year))
    return s


def search_records(search_params, s):
    if search_params and "author" in search_params:
        s = s.query(
            "nested",
            path="affiliations",
            query=Q(
                "match_phrase",
                affiliations__author_display_name={
                    "query": search_params["author"],
                    "slop": 1,
                },
            ),
        )
    if search_params and "journal_title" in search_params:
        s = s.query(
            "match_phrase",
            journal__title={"query": search_params["journal_title"], "slop": 1},
        )
    if search_params and "publisher" in search_params:
        s = s.query("match", journal__publisher=search_params["publisher"])
    if search_params and "title" in search_params:
        # alternate method
        # q = (
        #     Q("match", work_title={"query": search_params["title"]})
        #     | Q("match", work_title={"query": search_params["title"], "operator": "and"})
        #     | Q("match_phrase", work_title={"query": search_params["title"], "boost": 2})
        # )
        # s = s.query(q)
        s = s.query(
            "match_phrase", work_title={"query": search_params["title"], "slop": 1}
        )
    return s


def group_by_records(group_by, s, group_by_size):
    if group_by and group_by == "author_id":
        a = A("terms", field="author_ids", size=group_by_size)
        s.aggs.bucket("groupby", a)

    if group_by and group_by == "country":
        s.aggs.bucket("affiliations", Nested(path="affiliations")).bucket(
            "groupby", Terms(field="affiliations.country")
        )

    if group_by and group_by == "issn":
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
