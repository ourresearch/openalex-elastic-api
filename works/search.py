from elasticsearch_dsl import A, Q
from elasticsearch_dsl.aggs import Terms, Nested


def filter_records(filters, s):
    if filters and "author_id" in filters:
        s = s.filter(
            "nested",
            path="affiliations",
            query=Q("term", affiliations__author_id=int(filters["author_id"])),
        )
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
            query=Q("match_phrase", affiliations__author_display_name=search_params["author"]),
        )
    if search_params and "journal_title" in search_params:
        s = s.query("match", journal__title=search_params["journal_title"])
    if search_params and "publisher" in search_params:
        s = s.query("match", journal__publisher=search_params["publisher"])
    if search_params and "title" in search_params:
        s = s.query("match_phrase", work_title=search_params["title"])
    return s


def group_by_records(group_by, s):
    if group_by and group_by == "year":
        a = A("terms", field="year")
        s.aggs.bucket("groupby", a)

    if group_by and group_by == "issn":
        a = A("terms", field="journal.all_issns")
        s.aggs.bucket("groupby", a)

    if group_by and group_by == "author_id":
        s.aggs.bucket("affiliations", Nested(path="affiliations")).bucket(
            "groupby", Terms(field="affiliations.author_id")
        )

    if not group_by:
        # sort
        s = s.sort("-year")
    return s
