from collections import OrderedDict

import iso3166
import pycountry
from elasticsearch_dsl import A, MultiSearch, Q, Search
from iso4217 import Currency

import settings
from core.exceptions import APIQueryParamsError
from core.search import full_search_query
from core.utils import (get_display_names, get_display_names_award_ids,
                        get_display_names_host_organization)
from countries import COUNTRIES_BY_CONTINENT, GLOBAL_SOUTH_COUNTRIES


def group_by_records(field, s, sort_params, known, per_page, q):
    group_by_field = field.alias if field.alias else field.es_sort_field()
    if type(field).__name__ == "RangeField" or type(field).__name__ == "BooleanField":
        missing = -111
    else:
        missing = "unknown"

    if q:
        per_page = 500
        shard_size = 5000
    else:
        shard_size = 3000

    if (
        field.param == "repository"
        or field.param == "locations.source.host_institution_lineage"
    ):
        s = s.filter("term", **{"locations.source.type": "repository"})
    if field.param == "journal":
        s = s.filter("term", **{"primary_location.source.type": "journal"})

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
            s.aggs.bucket("groupby", a)
    elif "is_global_south" in field.param:
        country_codes = [c["country_code"] for c in GLOBAL_SOUTH_COUNTRIES]
        exists = A("filter", Q("terms", **{group_by_field: country_codes}))
        not_exists = A("filter", ~Q("terms", **{group_by_field: country_codes}))
        s.aggs.bucket("exists", exists)
        s.aggs.bucket("not_exists", not_exists)
    elif (
        field.param in settings.EXTERNAL_ID_FIELDS
        or field.param in settings.BOOLEAN_TEXT_FIELDS
    ):
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
        s.aggs.bucket("groupby", a)
    else:
        a = A(
            "terms",
            field=group_by_field,
            missing=missing,
            size=per_page,
            shard_size=shard_size,
        )
        s.aggs.bucket("groupby", a)
    return s


def group_by_continent(
    field, index_name, search, filter_params, filter_records, fields_dict, q
):
    group_by_results = []
    took = 0
    ms = MultiSearch(index=index_name)
    for continent in COUNTRIES_BY_CONTINENT:
        s = Search()
        if search and search != '""':
            search_query = full_search_query(index_name, search)
            s = s.query(search_query)

        # filter
        if filter_params:
            s = filter_records(fields_dict, filter_params, s)
        s = s.extra(track_total_hits=True)
        country_codes = [c["country_code"] for c in COUNTRIES_BY_CONTINENT[continent]]
        s = s.filter("terms", **{field.es_field(): country_codes})
        ms = ms.add(s)

    responses = ms.execute()

    for continent, response in zip(COUNTRIES_BY_CONTINENT.keys(), responses):
        if not q or q and q.lower() in continent.lower():
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
        search_query = full_search_query(index_name, search)
        s = s.query(search_query)

    # filter
    if filter_params:
        s = filter_records(fields_dict, filter_params, s)
    s = s.query(~Q("exists", field=field.es_field()))
    response = s.execute()
    unknown_count = s.count()
    if (unknown_count and not q) or (unknown_count and q and q.lower() in "unknown"):
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
    buckets = response.aggregations.groupby.buckets
    if (
        group_by.endswith(".id")
        or group_by.endswith("host_organization")
        or group_by.endswith("repository")
        or group_by.endswith("journal")
        or group_by.endswith("host_organization_lineage")
        or group_by.endswith("host_institution_lineage")
        or group_by.endswith("publisher_lineage")
        or group_by.endswith("ids")
        or group_by == "grants.award_id"
        or group_by == "grants.funder"
    ):
        if group_by.endswith("host_institution_lineage"):
            buckets = keep_institution_buckets(buckets)
        elif group_by.endswith("publisher_lineage"):
            buckets = keep_publisher_buckets(buckets)
        keys = [b.key for b in buckets]
        if group_by.endswith("host_organization") or group_by.endswith(
            "host_organization_lineage"
        ):
            ids_to_display_names = get_display_names_host_organization(keys)
        elif group_by == "grants.award_id":
            ids_to_display_names = get_display_names_award_ids(keys)
        else:
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
    elif group_by == "apc_payment.provenance":
        for b in buckets:
            if b.key == "unknown":
                key_display_name = "unknown"
            elif b.key == "doaj":
                key_display_name = (
                    "Directory of Open Access Journals (DOAJ) at https://doaj.org"
                )
            elif b.key == "openapc":
                key_display_name = "OpenAPC at https://openapc.net"
            group_by_results.append(
                {
                    "key": b.key,
                    "key_display_name": key_display_name,
                    "doc_count": b.inner.doc_count if "inner" in b else b.doc_count,
                }
            )
    elif group_by.endswith("currency"):
        for b in buckets:
            if b.key == "unknown":
                key_display_name = "unknown"
            else:
                # convert currency code to full description
                key_display_name = Currency(b.key).currency_name
            group_by_results.append(
                {
                    "key": b.key,
                    "key_display_name": key_display_name,
                    "doc_count": b.inner.doc_count if "inner" in b else b.doc_count,
                }
            )
    elif group_by == "language":
        for b in buckets:
            if b.key == "unknown":
                key_display_name = "unknown"
            elif b.key.lower() == "zh-cn":
                key_display_name = "Chinese"
            else:
                language = pycountry.languages.get(alpha_2=b.key.lower())
                key_display_name = language.name if language else None
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


def keep_institution_buckets(buckets):
    buckets_to_keep = []
    for b in buckets:
        if (
            b["key"]
            and b["key"].startswith("https://openalex.org/I")
            or b["key"] == "unknown"
        ):
            buckets_to_keep.append(b)
    return buckets_to_keep


def keep_publisher_buckets(buckets):
    buckets_to_keep = []
    for b in buckets:
        if b["key"] and b["key"].startswith("https://openalex.org/P"):
            buckets_to_keep.append(b)
    return buckets_to_keep


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
    field, index_name, search, filter_params, filter_records, fields_dict, q
):
    group_by_results = []
    took = 0
    ms = MultiSearch(index=index_name)
    for version in settings.VERSIONS:
        s = Search()
        if search and search != '""':
            search_query = full_search_query(index_name, search)
            s = s.query(search_query)

        # filter
        if filter_params:
            s = filter_records(fields_dict, filter_params, s)
        s = s.extra(track_total_hits=True)
        if version == "null":
            s = s.filter(~Q("exists", field="locations.version"))
        else:
            kwargs1 = {"locations.version": version}
            s = s.query(Q("term", **kwargs1))
        ms = ms.add(s)

    responses = ms.execute()

    for version, response in zip(settings.VERSIONS, responses):
        version = "unknown" if version == "null" else version
        key_display_name = "unknown" if version == "null" else version
        if not q or q and q.lower() in version.lower():
            group_by_results.append(
                {
                    "key": version,
                    "key_display_name": key_display_name,
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


def group_by_best_open_version(
    field, index_name, search, filter_params, filter_records, fields_dict, q
):
    group_by_results = []
    took = 0
    ms = MultiSearch(index=index_name)
    versions = ["any", "acceptedOrPublished", "published"]
    for version in versions:
        s = Search()
        if search and search != '""':
            search_query = full_search_query(index_name, search)
            s = s.query(search_query)

        # filter
        if filter_params:
            s = filter_records(fields_dict, filter_params, s)
        s = s.extra(track_total_hits=True)
        submitted_query = Q("term", best_oa_location__version="submittedVersion")
        accepted_query = Q("term", best_oa_location__version="acceptedVersion")
        published_query = Q("term", best_oa_location__version="publishedVersion")
        if version == "any":
            query = submitted_query | accepted_query | published_query
        elif version == "acceptedOrPublished":
            query = accepted_query | published_query
        elif version == "published":
            query = published_query
        ms = ms.add(s.filter(query))

    responses = ms.execute()

    for version, response in zip(versions, responses):
        key_display_name = version
        if not q or q and q.lower() in version.lower():
            group_by_results.append(
                {
                    "key": version,
                    "key_display_name": key_display_name,
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
        "ancestors.id": "ancestors__display_name__autocomplete",
        "authorships.institutions.id": "authorships__institutions__display_name__autocomplete",
        "authorships.author.id": "authorships__author__display_name__autocomplete",
        "best_oa_location.source.id": "best_oa_location__source__display_name__autocomplete",
        "concept.id": "concepts__display_name__autocomplete",
        "concepts.id": "concepts__display_name__autocomplete",
        "corresponding_author_ids": "authorships__author__display_name__autocomplete",
        "corresponding_institution_ids": "authorships__institutions__display_name__autocomplete",
        "journal": "locations__source__display_name__autocomplete",
        "last_known_institution.id": "last_known_institution__display_name__autocomplete",
        "locations.source.id": "locations__source__display_name__autocomplete",
        "locations.source.publisher_lineage": "locations__source__host_organization_lineage_names__autocomplete",
        "primary_location.source.id": "primary_location__source__display_name__autocomplete",
        "publisher": "publisher__autocomplete",
        "repository": "locations__source__display_name__autocomplete",
    }
    if autocomplete_field_mapping.get(group_by):
        if "author.id" in group_by:
            # allows us to ignore middle initials in names
            slop = 1
        else:
            slop = 0
        field = autocomplete_field_mapping[group_by]
        query = Q("match_phrase_prefix", **{field: {"query": q, "slop": slop}})
        s = s.query(query)
    elif "country_code" in group_by:
        country_codes = country_search(q)
        s = s.query("terms", **{field.es_field(): country_codes})
    elif group_by == "publication_year":
        min_year, max_year = set_year_min_max(q)
        kwargs = {"publication_year": {"gte": min_year, "lte": max_year}}
        s = s.query("range", **kwargs)
    elif (
        "author" in group_by
        or group_by == "grants.funder"
        or group_by.endswith("host_institution_lineage")
        or group_by.endswith("host_organization")
        or group_by.endswith("host_organization_lineage")
        or "institution" in group_by
        or group_by == "lineage"
        or group_by.endswith("publisher_lineage")
        or group_by == "repository"
        or group_by == "language"
    ):
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
    range_field_exceptions = [
        "apc_usd",
        "apc_list.value",
        "apc_list.value_usd",
        "apc_paid.value",
        "apc_paid.value_usd",
        "authors_count",
        "cited_by_count",
        "concepts_count",
        "hierarchy_level",
        "grants_count",
        "level",
        "locations_count",
        "publication_year",
        "summary_stats.2yr_mean_citedness",
        "summary_stats.h_index",
        "summary_stats.i10_index",
        "works_count",
    ]
    if (
        type(field).__name__ == "DateField"
        or type(field).__name__ == "DateTimeField"
        or (
            type(field).__name__ == "RangeField"
            and field.param not in range_field_exceptions
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
