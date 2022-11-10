from collections import OrderedDict

import iso3166
from elasticsearch_dsl import A, MultiSearch, Q, Search

import settings
from core.exceptions import APIQueryParamsError
from core.utils import get_display_names
from countries import COUNTRIES_BY_CONTINENT, GLOBAL_SOUTH_COUNTRIES


def group_by_records(field, s, sort_params, known, per_page, q):
    group_by_field = field.alias if field.alias else field.es_sort_field()
    if type(field).__name__ == "RangeField" or type(field).__name__ == "BooleanField":
        missing = -111
    else:
        missing = "unknown"

    if q:
        per_page = 200
    shard_size = 3000

    if sort_params:
        for key, order in sort_params.items():
            if key == "count" and not known:
                a = A(
                    "terms",
                    field=group_by_field,
                    missing=missing,
                    order={"_count": order},
                    size=per_page,
                    shard_size=shard_size,
                )
            elif key == "count" and known:
                a = A(
                    "terms",
                    field=group_by_field,
                    order={"_count": order},
                    size=per_page,
                    shard_size=shard_size,
                )
            elif key == "key" and not known:
                a = A(
                    "terms",
                    field=group_by_field,
                    missing=missing,
                    order={"_key": order},
                    size=per_page,
                    shard_size=shard_size,
                )
            elif key == "key" and known:
                a = A(
                    "terms",
                    field=group_by_field,
                    order={"_key": order},
                    size=per_page,
                    shard_size=shard_size,
                )
            if field.nested:
                s.aggs.bucket("nested_groupby", "nested", path="authorships").bucket(
                    "groupby", a
                )
            else:
                s.aggs.bucket("groupby", a)
    elif "is_global_south" in field.param:
        country_codes = [c["country_code"] for c in GLOBAL_SOUTH_COUNTRIES]
        if field.nested:
            exists = A(
                "filter",
                Q(
                    "nested",
                    path="authorships",
                    query=Q("terms", **{group_by_field: country_codes}),
                ),
            )
            not_exists = A(
                "filter",
                Q(
                    "nested",
                    path="authorships",
                    query=~Q("terms", **{group_by_field: country_codes}),
                ),
            )
            s.aggs.bucket("exists", exists)
            s.aggs.bucket("not_exists", not_exists)
        else:
            exists = A("filter", Q("terms", **{group_by_field: country_codes}))
            not_exists = A("filter", ~Q("terms", **{group_by_field: country_codes}))
            s.aggs.bucket("exists", exists)
            s.aggs.bucket("not_exists", not_exists)
    elif (
        field.param in settings.EXTERNAL_ID_FIELDS
        or field.param in settings.BOOLEAN_TEXT_FIELDS
    ):
        if field.nested:
            exists = A(
                "filter",
                Q(
                    "nested",
                    path="authorships",
                    query=Q("exists", field=group_by_field),
                ),
            )
            not_exists = A(
                "filter",
                ~Q(
                    "nested",
                    path="authorships",
                    query=Q("exists", field=group_by_field),
                ),
            )
        else:
            exists = A("filter", Q("exists", field=group_by_field))
            not_exists = A("filter", ~Q("exists", field=group_by_field))
        s.aggs.bucket("exists", exists)
        s.aggs.bucket("not_exists", not_exists)
    elif known:
        a = A(
            "terms",
            field=group_by_field,
            size=per_page,
            shard_size=shard_size,
        )
        if field.nested:
            s.aggs.bucket("nested_groupby", "nested", path="authorships").bucket(
                "groupby", a
            )
        else:
            s.aggs.bucket("groupby", a)
    else:
        a = A(
            "terms",
            field=group_by_field,
            missing=missing,
            size=per_page,
            shard_size=shard_size,
        )
        if field.nested:
            if "author.id" in field.param and q:
                s.aggs.bucket("nested_groupby", "nested", path="authorships").bucket(
                    "inner",
                    "filter",
                    Q(
                        "match_phrase_prefix",
                        **{
                            "authorships__author__display_name__autocomplete": {
                                "query": q,
                                "slop": 1,
                                "max_expansions": 1000,
                            }
                        },
                    ),
                ).bucket("groupby", a)
            elif (
                q
                and "institutions.id" in field.param
                or q
                and "institution.id" in field.param
            ):
                s.aggs.bucket("nested_groupby", "nested", path="authorships").bucket(
                    "inner",
                    "filter",
                    Q(
                        "match_phrase_prefix",
                        **{
                            "authorships__institutions__display_name__autocomplete": {
                                "query": q,
                                "max_expansions": 500,
                            }
                        },
                    ),
                ).bucket("groupby", a)
            else:
                s.aggs.bucket("nested_groupby", "nested", path="authorships").bucket(
                    "groupby",
                    A(
                        "terms",
                        field=group_by_field,
                        missing=missing,
                        size=per_page,
                        order={"inner": "desc"},
                        shard_size=shard_size,
                    ),
                ).bucket("inner", "reverse_nested")
        else:
            s.aggs.bucket("groupby", a)
    return s


def group_by_continent(
    field,
    index_name,
    search,
    full_search,
    filter_params,
    filter_records,
    fields_dict,
):
    group_by_results = []
    took = 0
    ms = MultiSearch(index=index_name)
    for continent in COUNTRIES_BY_CONTINENT:
        s = Search()
        if search and search != '""':
            s = full_search(index_name, s, search)

        # filter
        if filter_params:
            s = filter_records(fields_dict, filter_params, s)
        s = s.extra(track_total_hits=True)
        country_codes = [c["country_code"] for c in COUNTRIES_BY_CONTINENT[continent]]
        if field.nested:
            s = s.filter(
                "nested",
                path="authorships",
                query=Q("terms", **{field.es_field(): country_codes}),
            )
        else:
            s = s.filter("terms", **{field.es_field(): country_codes})
        ms = ms.add(s)

    responses = ms.execute()

    for continent, response in zip(COUNTRIES_BY_CONTINENT.keys(), responses):
        group_by_results.append(
            {
                "key": settings.CONTINENT_PARAMS.get(
                    continent.lower().replace(" ", "_")
                ),
                "key_display_name": continent,
                "doc_count": response.hits.total.value,
            }
        )
        took = took + response.took

    # get unknown
    s = Search(index=index_name)
    if search and search != '""':
        s = full_search(index_name, s, search)

    # filter
    if filter_params:
        s = filter_records(fields_dict, filter_params, s)
    if field.nested:
        s = s.query(
            ~Q(
                "nested",
                path="authorships",
                query=Q("exists", field=field.es_field()),
            )
        )
    else:
        s = s.query(~Q("exists", field=field.es_field()))
    response = s.execute()
    unknown_count = s.count()
    if unknown_count:
        group_by_results.append(
            {
                "key": "unknown",
                "key_display_name": "unknown",
                "doc_count": unknown_count,
            }
        )
    took = took + response.took

    # sort by count
    group_by_results = sorted(
        group_by_results, key=lambda d: d["doc_count"], reverse=True
    )

    result = OrderedDict()
    result["meta"] = {
        "count": len(group_by_results),
        "db_response_time_ms": took,
        "page": 1,
        "per_page": 10,
    }
    result["results"] = []
    result["group_by"] = group_by_results
    return result


def get_group_by_results(group_by, response):
    group_by_results = []
    if (
        "nested_groupby" in response.aggregations
        and "inner" in response.aggregations.nested_groupby
    ):
        buckets = response.aggregations.nested_groupby.inner.groupby.buckets
    elif "nested_groupby" in response.aggregations:
        buckets = response.aggregations.nested_groupby.groupby.buckets
    else:
        buckets = response.aggregations.groupby.buckets
    if group_by.endswith(".id"):
        keys = [b.key for b in buckets]
        ids_to_display_names = get_display_names(keys)
        for b in buckets:
            if b.key == "unknown":
                key_display_name = "unknown"
            else:
                key_display_name = ids_to_display_names.get(b.key)
            group_by_results.append(
                {
                    "key": b.key,
                    "key_display_name": key_display_name,
                    "doc_count": b.inner.doc_count if "inner" in b else b.doc_count,
                }
            )
    elif group_by.endswith("country_code"):
        for b in buckets:
            if b.key == "unknown":
                key_display_name = "unknown"
            else:
                country = iso3166.countries.get(b.key.lower())
                key_display_name = country.name if country else None
            group_by_results.append(
                {
                    "key": b.key,
                    "key_display_name": key_display_name,
                    "doc_count": b.inner.doc_count if "inner" in b else b.doc_count,
                }
            )
    else:
        for b in buckets:
            if b.key == -111:
                key = "unknown"
            elif "key_as_string" in b:
                key = b.key_as_string
            else:
                key = b.key
            group_by_results.append(
                {
                    "key": key,
                    "key_display_name": key,
                    "doc_count": b.inner.doc_count if "inner" in b else b.doc_count,
                }
            )
    return group_by_results


def get_group_by_results_external_ids(response):
    exists_count = response.aggregations.exists.doc_count
    not_exists_count = response.aggregations.not_exists.doc_count

    group_by_results = [
        {
            "key": "true",
            "key_display_name": "true",
            "doc_count": exists_count,
        },
        {
            "key": "false",
            "key_display_name": "false",
            "doc_count": not_exists_count,
        },
    ]
    return group_by_results


def group_by_version(
    field,
    index_name,
    search,
    full_search,
    filter_params,
    filter_records,
    fields_dict,
):
    group_by_results = []
    took = 0
    ms = MultiSearch(index=index_name)
    for version in settings.VERSIONS:
        s = Search()
        if search and search != '""':
            s = full_search(index_name, s, search)

        # filter
        if filter_params:
            s = filter_records(fields_dict, filter_params, s)
        s = s.extra(track_total_hits=True)
        if version == "null":
            s = s.filter(
                ~Q("exists", field="host_venue.version")
                & ~Q("exists", field="alternate_host_venues.version")
            )
        else:
            kwargs1 = {"host_venue.version": version}
            kwargs2 = {"alternate_host_venues.version": version}
            s = s.query(Q("term", **kwargs1) | Q("term", **kwargs2))
        ms = ms.add(s)

    responses = ms.execute()

    for version, response in zip(settings.VERSIONS, responses):
        group_by_results.append(
            {
                "key": version,
                "key_display_name": version,
                "doc_count": response.hits.total.value,
            }
        )
        took = took + response.took

    # sort by count
    group_by_results = sorted(
        group_by_results, key=lambda d: d["doc_count"], reverse=True
    )

    result = OrderedDict()
    result["meta"] = {
        "count": len(group_by_results),
        "db_response_time_ms": took,
        "page": 1,
        "per_page": 10,
    }
    result["results"] = []
    result["group_by"] = group_by_results
    return result


def group_by_records_transform(field, parent_index, sort_params):
    index_name = get_transform_index(field, parent_index)
    s = Search(index=index_name)
    s = s.query("match_all").extra(size=200)

    if sort_params:
        for key, order in sort_params.items():
            if key == "count" and order == "desc":
                s = s.sort("-doc_count")
            elif key == "count" and order == "asc":
                s = s.sort("doc_count")
            elif key == "key" and order == "desc":
                s = s.sort("-key")
            elif key == "key" and order == "asc":
                s = s.sort("key")
    else:
        s = s.sort("-doc_count")
    return s


def get_group_by_results_transform(group_by, response):
    group_by_results = []
    if group_by.endswith(".id"):
        keys = []
        for b in response:
            if b.key:
                keys.append(b.key)
        ids_to_display_names = get_display_names(keys)
        for b in response:
            if b.key:
                key = b.key
                key_display_name = ids_to_display_names.get(b.key)
            else:
                key = "unknown"
                key_display_name = "unknown"
            group_by_results.append(
                {
                    "key": key,
                    "key_display_name": key_display_name,
                    "doc_count": b.doc_count,
                }
            )
    else:
        for b in response:
            if b.key == -111:
                key = "unknown"
            elif "key_as_string" in b:
                key = b.key_as_string
            else:
                key = b.key
            group_by_results.append(
                {"key": key, "key_display_name": key, "doc_count": b.doc_count}
            )
    return group_by_results


def filter_group_by(field, group_by, q, s):
    """Reduce records that will be grouped based on q param."""
    autocomplete_field_mapping = {
        "alternate_host_venues.id": "alternate_host_venues__display_name",
        "ancestors.id": "ancestors__display_name__autocomplete",
        "concept.id": "concepts__display_name__autocomplete",
        "concepts.id": "concepts__display_name__autocomplete",
        "host_venue.display_name": "host_venue__display_name__autocomplete",
        "host_venue.id": "host_venue__display_name__autocomplete",
        "host_venue.publisher": "host_venue__publisher__autocomplete",
        "journal.id": "host_venue__display_name__autocomplete",
    }
    if autocomplete_field_mapping.get(group_by):
        field = autocomplete_field_mapping[group_by]
        s = s.query("match_phrase_prefix", **{field: q})
    elif "country_code" in group_by:
        country_codes = country_search(q)
        if field.nested:
            q = Q(
                "nested",
                path="authorships",
                query=Q("terms", **{field.es_field(): country_codes}),
            )
            s = s.query(q)
        else:
            s = s.query("terms", **{field.es_field(): country_codes})
    elif group_by == "publication_year":
        min_year, max_year = set_year_min_max(q)
        kwargs = {"publication_year": {"gte": min_year, "lte": max_year}}
        s = s.query("range", **kwargs)
    elif "author" in group_by or "institution" in group_by:
        return s
    else:
        s = s.query("prefix", **{field.es_field(): q.lower()})
    return s


def search_group_by_results(group_by, q, result, per_page):
    filtered_result = []
    for i, r in enumerate(result):
        if len(filtered_result) == per_page:
            break
        if "author.id" in group_by:
            if all(x in str(r["key_display_name"]).lower() for x in q.lower().split()):
                filtered_result.append(r)
        else:
            if q.lower() in str(r["key_display_name"]).lower():
                filtered_result.append(r)
    return filtered_result


def is_transform(field, parent_index, filter_params):
    if filter_params:
        return False

    for transform in settings.TRANSFORMS:
        if field.param == transform["field"] and parent_index.startswith(
            transform["parent_index"]
        ):
            return True


def get_transform_index(field, parent_index):
    for transform in settings.TRANSFORMS:
        if field.param == transform["field"] and parent_index.startswith(
            transform["parent_index"]
        ):
            return transform["index_name"]


def country_search(q):
    country_names = [n for n in iso3166.countries_by_name.keys()]
    matching_country_codes = []
    for country_name in country_names:
        if country_name.startswith(q.upper()):
            matching_country_codes.append(
                iso3166.countries_by_name[country_name].alpha2
            )
    return matching_country_codes


def set_year_min_max(q):
    min_year = 1000
    max_year = 3000
    if str(q).startswith("1") and len(q) == 1:
        min_year = 1000
        max_year = 1999
    elif str(q).startswith("2") and len(q) == 1:
        min_year = 2000
        max_year = 2999
    elif len(q) == 2:
        min_year = int(q) * 100
        max_year = int(q) * 100 + 99
    elif len(q) == 3:
        min_year = int(q) * 10
        max_year = int(q) * 10 + 9
    elif len(q) == 4:
        min_year = int(q)
        max_year = int(q)
    return min_year, max_year


def validate_group_by(field):
    if (
        type(field).__name__ == "DateField"
        or (
            type(field).__name__ == "RangeField"
            and field.param != "cited_by_count"
            and field.param != "level"
            and field.param != "publication_year"
            and field.param != "works_count"
            and field.param != "authors_count"
            and field.param != "concepts_count"
        )
        or type(field).__name__ == "SearchField"
    ):
        raise APIQueryParamsError("Cannot group by date, number, or search fields.")
    elif field.param == "referenced_works":
        raise APIQueryParamsError(
            "Group by referenced_works is not supported at this time."
        )
    elif field.param in settings.DO_NOT_GROUP_BY:
        raise APIQueryParamsError(f"Cannot group by {field.param}.")
