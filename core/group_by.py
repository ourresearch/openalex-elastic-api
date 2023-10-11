import iso3166
import pycountry
from elasticsearch_dsl import A, Q
from iso4217 import Currency

import settings
from core.custom_group_bys import (
    group_by_continent,
    group_by_version,
    group_by_best_open_version,
)
from core.exceptions import APIQueryParamsError
from core.utils import (
    get_display_names,
    get_display_names_award_ids,
    get_display_names_host_organization,
    get_display_names_sdgs,
    get_field,
    get_all_groupby_values,
)
from core.preference import clean_preference
from countries import GLOBAL_SOUTH_COUNTRIES


def group_by_records(group_by, field, s, sort_params, known, per_page, q):
    group_by_field = field.alias if field.alias else field.es_sort_field()
    bucket_key = f"groupby_{group_by.replace('.', '_')}"
    exists_bucket_key = f"exists_{group_by.replace('.', '_')}"
    not_exists_bucket_key = f"not_exists_{group_by.replace('.', '_')}"
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
            s.aggs.bucket(bucket_key, a)
    elif "is_global_south" in field.param:
        country_codes = [c["country_code"] for c in GLOBAL_SOUTH_COUNTRIES]
        exists = A("filter", Q("terms", **{group_by_field: country_codes}))
        not_exists = A("filter", ~Q("terms", **{group_by_field: country_codes}))
        s.aggs.bucket(exists_bucket_key, exists)
        s.aggs.bucket(not_exists_bucket_key, not_exists)
    elif (
        field.param in settings.EXTERNAL_ID_FIELDS
        or field.param in settings.BOOLEAN_TEXT_FIELDS
    ):
        exists = A("filter", Q("exists", field=group_by_field))
        not_exists = A("filter", ~Q("exists", field=group_by_field))
        s.aggs.bucket(exists_bucket_key, exists)
        s.aggs.bucket(not_exists_bucket_key, not_exists)
    elif known:
        a = A(
            "terms",
            field=group_by_field,
            size=per_page,
            shard_size=shard_size,
        )
        s.aggs.bucket(bucket_key, a)
    else:
        a = A(
            "terms",
            field=group_by_field,
            missing=missing,
            size=per_page,
            shard_size=shard_size,
        )
        s.aggs.bucket(bucket_key, a)
    return s


def get_group_by_results(group_by, response):
    group_by_results = []
    buckets = response.aggregations[f"groupby_{group_by.replace('.', '_')}"].buckets
    if (
        group_by.endswith(".id")
        or group_by.endswith("host_organization")
        or group_by.endswith("repository")
        or group_by.endswith("journal")
        or group_by.endswith("host_organization_lineage")
        or group_by.endswith("host_institution_lineage")
        or group_by.endswith("publisher_lineage")
        or group_by.endswith("ids")
        or group_by == "authorships.institutions.lineage"
        or group_by == "grants.award_id"
        or group_by == "grants.funder"
        or group_by == "last_known_institution.lineage"
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
        elif group_by == "sustainable_development_goals.id":
            ids_to_display_names = get_display_names_sdgs(keys)
        else:
            ids_to_display_names = get_display_names(keys)
        for b in buckets:
            if b.key == "unknown":
                key_display_name = "unknown"
            else:
                key_display_name = ids_to_display_names.get(b.key)
            if (
                group_by == "authorships.author.id" or group_by == "author.id"
            ) and not key_display_name:
                # do not include null authors
                continue
            group_by_results.append(
                {
                    "key": b.key,
                    "key_display_name": key_display_name,
                    "doc_count": b.inner.doc_count if "inner" in b else b.doc_count,
                }
            )
    elif group_by.endswith("country_code") or group_by.endswith("countries"):
        for b in buckets:
            if b.key == "unknown":
                key_display_name = "unknown"
            else:
                try:
                    country = iso3166.countries.get(b.key.lower())
                except KeyError:
                    country = None
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


def get_group_by_results_external_ids(response, group_by):
    exists_count = response.aggregations[
        f"exists_{group_by.replace('.', '_')}"
    ].doc_count
    not_exists_count = response.aggregations[
        f"not_exists_{group_by.replace('.', '_')}"
    ].doc_count

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
        or group_by == "sustainable_development_goals.id"
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
        "countries_distinct_count",
        "institutions_distinct_count",
        "locations_count",
        "publication_year",
        "referenced_works_count",
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


def parse_group_by(group_by):
    known = False
    if ":" in group_by:
        group_by_split = group_by.split(":")
        if len(group_by_split) == 2 and group_by_split[1].lower() == "known":
            group_by = group_by_split[0]
            known = True
        elif len(group_by_split) == 2 and group_by_split[1].lower() != "known":
            raise APIQueryParamsError(
                "The only valid filter for a group_by param is 'known', which hides the unknown group from results."
            )
    return group_by, known


def process_group_by_item(fields_dict, group_by_item, s, params):
    s = s.params(preference=clean_preference(group_by_item))
    group_by_item, known = parse_group_by(group_by_item)
    field = get_field(fields_dict, group_by_item)
    validate_group_by(field)
    if (
        field.param != "best_open_version"
        or field.param != "version"
        or "continent" not in field.param
    ):
        s = group_by_records(
            group_by_item,
            field,
            s,
            params["sort"],
            known,
            params["per_page"],
            params["q"],
        )
    return s


def handle_group_by_logic(
    group_by,
    params,
    index_name,
    fields_dict,
    response,
):
    field = get_field(fields_dict, group_by)
    if (
        group_by in settings.EXTERNAL_ID_FIELDS
        or group_by in settings.BOOLEAN_TEXT_FIELDS
        or "is_global_south" in group_by
    ):
        return get_group_by_results_external_ids(response, group_by)
    elif "continent" in field.param:
        results = group_by_continent(
            field,
            index_name,
            params["search"],
            params["filters"],
            fields_dict,
            params["q"],
        )
    elif field.param == "version":
        results = group_by_version(
            field,
            index_name,
            params["search"],
            params["filters"],
            fields_dict,
            params["q"],
        )
    elif field.param == "best_open_version":
        results = group_by_best_open_version(
            field,
            index_name,
            params["search"],
            params["filters"],
            fields_dict,
            params["q"],
        )
    else:
        results = get_group_by_results(group_by, response)
    return results


def add_zero_values(results, known, index_name, field):
    ignore_values = set([item["key"] for item in results])
    if known:
        ignore_values.update(["unknown", "-111"])
    possible_buckets = get_all_groupby_values(
        entity=index_name.split("-")[0], field=field
    )
    for bucket in possible_buckets:
        if bucket["key"] not in ignore_values and not bucket["key"].startswith(
            "http://metadata.un.org"
        ):
            results.append(
                {
                    "key": bucket["key"],
                    "key_display_name": bucket["key_display_name"],
                    "doc_count": 0,
                }
            )
    return results


def search_group_by_strings_with_q(params, result):
    result["meta"]["q"] = params["q"]
    if params["group_by"] and params["q"] and params["q"] != "''":
        result["group_by"] = search_group_by_results(
            params["group_by"], params["q"], result["group_by"], params["per_page"]
        )
        result["meta"]["count"] = len(result["group_by"])
    elif params["group_bys"] and params["q"] and params["q"] != "''":
        for group_by_item in params["group_bys"]:
            group_by_item, _ = parse_group_by(group_by_item)
            for group in result["group_bys"]:
                if group["group_by_key"] == group_by_item:
                    group["groups"] = search_group_by_results(
                        group_by_item,
                        params["q"],
                        group["groups"],
                        params["per_page"],
                    )
                    break
    return result
