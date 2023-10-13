import iso3166
import pycountry
from iso4217 import Currency

import settings
from core.group_by.custom_results import group_by_continent, group_by_version, group_by_best_open_version

from core.utils import (
    get_field,
)
from group_by.utils import get_all_groupby_values
from core.group_by.display_names import get_display_names, get_display_names_host_organization, \
    get_display_names_award_ids, get_display_names_sdgs


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
