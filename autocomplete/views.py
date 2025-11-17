from collections import OrderedDict

import iso3166
from elasticsearch_dsl import A, Search
from flask import Blueprint, request

from authors.fields import fields_dict as authors_fields_dict
from autocomplete.schemas import MessageAutocompleteCustomSchema, MessageSchema
from autocomplete.shared import (
    search_canonical_id_full,
    single_entity_autocomplete,
)
from autocomplete.utils import (
    AUTOCOMPLETE_SOURCE,
    strip_punctuation,
)
from autocomplete.full import (
    get_indices,
    get_filter_results,
    build_full_search_query,
)
from autocomplete.validate import validate_full_autocomplete_params
from concepts.fields import fields_dict as concepts_fields_dict
from core.exceptions import APIQueryParamsError
from core.preference import clean_preference
from core.utils import get_data_version_connection
from funders.fields import fields_dict as funders_fields_dict
from institutions.fields import fields_dict as institutions_fields_dict
from keywords.fields import fields_dict as keywords_fields_dict
from licenses.fields import fields_dict as licenses_fields_dict
from subfields.fields import fields_dict as subfields_fields_dict
from publishers.fields import fields_dict as publishers_fields_dict
from settings import (
    AUTHORS_INDEX,
    CONCEPTS_INDEX,
    DEFAULT_DATA_VERSION,
    FUNDERS_INDEX,
    INSTITUTIONS_INDEX,
    KEYWORDS_INDEX,
    LICENSES_INDEX,
    PUBLISHERS_INDEX,
    SOURCES_INDEX,
    SUBFIELDS_INDEX,
    TOPICS_INDEX,
    WORKS_INDEX_LEGACY,
    WORKS_INDEX_WALDEN
)
from sources.fields import fields_dict as sources_fields_dict
from topics.fields import fields_dict as topics_fields_dict
from works.fields import fields_dict as works_fields_dict

blueprint = Blueprint("complete", __name__)


@blueprint.route("/autocomplete")
def autocomplete_full():
    validate_full_autocomplete_params(request)
    q = request.args.get("q")
    hide_works = request.args.get("hide_works")
    entity_type = request.args.get("entity_type")
    filter_results = []

    connection = get_data_version_connection(request)
    data_version = request.args.get('data_version') or request.args.get('data-version', DEFAULT_DATA_VERSION)
    entities_to_indeces = get_indices(data_version)
    if hide_works and hide_works.lower() == "true":
        entities_to_indeces.pop("work")
        sort = "-works_count"
    else:
        sort = "-cited_by_count"

    if entity_type:
        try:
            index = entities_to_indeces[entity_type]
        except KeyError:
            raise APIQueryParamsError(
                f"{entity_type} is not a valid value for parameter entity_type. Valid entity_type values are: {', '.join(entities_to_indeces.keys())}."
            )
    else:
        # remove concept from full autocomplete
        entities_to_indeces.pop("concept")

        if q and len(q) <= 5:
            entities = [
                entity
                for entity in entities_to_indeces.values()
                if "institution" in entity
                or "author" in entity
                or "countries" in entity
                or "licenses" in entity
            ]
            index = ",".join(entities)
        else:
            index = ",".join(entities_to_indeces.values())

    s = Search(index=index, using=connection)

    # Exclude deleted author ID
    s = s.exclude("term", ids__openalex="https://openalex.org/A5317838346")

    # filter xpac works for data version 2
    if connection == 'walden' and not hide_works:
        include_xpac = request.args.get('include_xpac') == 'true' or request.args.get('include-xpac') == 'true'
        if not include_xpac:
            s = s.exclude("term", is_xpac=True)

    if q:
        # canonical id match
        s, canonical_id_found = search_canonical_id_full(s, q)
        if not canonical_id_found:
            s = build_full_search_query(q, s, sort)
            filter_results = get_filter_results(q)

    s = s.source(AUTOCOMPLETE_SOURCE)
    preference = clean_preference(q)
    s = s.params(preference=preference)
    response = s.execute()

    result = OrderedDict()
    result["meta"] = {
        "count": s.count(),
        "db_response_time_ms": response.took,
        "page": 1,
        "per_page": 10,
    }
    result["results"] = response
    message_schema = MessageSchema()
    results = message_schema.dump(result)
    if filter_results:
        max_results_count = 10 - len(filter_results)

        # remove excess results from the end of the list
        results["results"] = results["results"][:max_results_count]

        # insert the filter_results at the beginning of the list
        results["results"] = filter_results + results["results"]
    return results


@blueprint.route("/autocomplete/authors")
def autocomplete_authors():
    connection = get_data_version_connection(request)
    index_name = AUTHORS_INDEX
    result = single_entity_autocomplete(authors_fields_dict, index_name, request, connection)
    message_schema = MessageSchema()
    return message_schema.dump(result)


@blueprint.route("/autocomplete/concepts")
def autocomplete_concepts():
    connection = get_data_version_connection(request)
    index_name = CONCEPTS_INDEX
    result = single_entity_autocomplete(concepts_fields_dict, index_name, request, connection)
    message_schema = MessageSchema()
    return message_schema.dump(result)


@blueprint.route("/autocomplete/funders")
def autocomplete_funders():
    connection = get_data_version_connection(request)
    index_name = FUNDERS_INDEX
    result = single_entity_autocomplete(funders_fields_dict, index_name, request, connection)
    message_schema = MessageSchema()
    return message_schema.dump(result)


@blueprint.route("/autocomplete/institutions")
def autocomplete_institutions():
    connection = get_data_version_connection(request)
    index_name = INSTITUTIONS_INDEX
    result = single_entity_autocomplete(institutions_fields_dict, index_name, request, connection)
    message_schema = MessageSchema()
    return message_schema.dump(result)


@blueprint.route("/autocomplete/topics")
def autocomplete_topics():
    connection = get_data_version_connection(request)
    index_name = TOPICS_INDEX
    result = single_entity_autocomplete(topics_fields_dict, index_name, request, connection)
    message_schema = MessageSchema()
    return message_schema.dump(result)


@blueprint.route("/autocomplete/works")
def autocomplete_works():
    connection = get_data_version_connection(request)
    data_version = request.args.get('data_version') or request.args.get('data-version', DEFAULT_DATA_VERSION)
    if data_version == '2':
        index_name = WORKS_INDEX_WALDEN
    else:
        index_name = WORKS_INDEX_LEGACY

    result = single_entity_autocomplete(works_fields_dict, index_name, request, connection)
    message_schema = MessageSchema()
    return message_schema.dump(result)


@blueprint.route("/autocomplete/publishers")
def autocomplete_publishers():
    connection = get_data_version_connection(request)
    index_name = PUBLISHERS_INDEX
    result = single_entity_autocomplete(publishers_fields_dict, index_name, request, connection)
    message_schema = MessageSchema()
    return message_schema.dump(result)


@blueprint.route("/autocomplete/sources")
def autocomplete_sources():
    connection = get_data_version_connection(request)
    index_name = SOURCES_INDEX
    result = single_entity_autocomplete(sources_fields_dict, index_name, request, connection)
    message_schema = MessageSchema()
    return message_schema.dump(result)


@blueprint.route("/autocomplete/keywords")
def autocomplete_keywords():
    connection = get_data_version_connection(request)
    index_name = KEYWORDS_INDEX
    result = single_entity_autocomplete(keywords_fields_dict, index_name, request, connection)
    message_schema = MessageSchema()
    return message_schema.dump(result)


@blueprint.route("/autocomplete/licenses")
def autocomplete_licenses():
    connection = get_data_version_connection(request)
    index_name = LICENSES_INDEX
    result = single_entity_autocomplete(licenses_fields_dict, index_name, request, connection)
    message_schema = MessageSchema()
    return message_schema.dump(result)

@blueprint.route("/autocomplete/subfields")
def autocomplete_subfields():
    connection = get_data_version_connection(request)
    index_name = SUBFIELDS_INDEX
    result = single_entity_autocomplete(subfields_fields_dict, index_name, request, connection)
    message_schema = MessageSchema()
    return message_schema.dump(result)


@blueprint.route("/autocomplete/institutions/country")
def autocomplete_institutions_country():
    q = request.args.get("q")
    q = strip_punctuation(q) if q else None
    if not q:
        raise APIQueryParamsError(
            f"Must enter a 'q' parameter in order to use autocomplete. Example: {request.url_rule}?q=my search"
        )

    connection = get_data_version_connection(request)

    # get countries and citation sums from elastic transform
    s = Search(index="institutions-countries-transform-v1", using=connection).extra(size=500)
    s = s.query("match_all")
    response = s.execute()
    country_sums = {
        h["_source"]["country_code"]["lower"]: int(
            h["_source"]["cited_by_count"]["sum"]
        )
        for h in response.hits.hits
    }

    found_countries = []
    for country, details in iso3166.countries_by_name.items():
        country_words = country.split()
        for word in country_words:
            # word in the country starts with our query, and the country is in the transform index
            if word.startswith(q.upper()) and country_sums.get(details.alpha2.lower()):
                found_countries.append(
                    OrderedDict(
                        {
                            "id": details.alpha2.upper(),
                            "display_name": details.name,
                            "cited_by_count": country_sums[details.alpha2.lower()],
                            "entity_type": "institution",
                            "external_id": None,
                        }
                    )
                )

    found_countries_sorted = sorted(
        found_countries, key=lambda item: item["cited_by_count"], reverse=True
    )

    result = OrderedDict()
    result["meta"] = {
        "count": len(found_countries_sorted),
        "db_response_time_ms": response.took,
        "page": 1,
        "per_page": 10,
    }
    result["results"] = found_countries_sorted[:10]
    message_schema = MessageAutocompleteCustomSchema()
    return message_schema.dump(result)


@blueprint.route("/autocomplete/institutions/type")
def autocomplete_institutions_type():
    q = request.args.get("q")
    q = strip_punctuation(q) if q else None
    q = q.lower() if q else None
    if not q:
        raise APIQueryParamsError(
            f"Must enter a 'q' parameter in order to use autocomplete. Example: {request.url_rule}?q=my search"
        )

    connection = get_data_version_connection(request)

    s = Search(index=INSTITUTIONS_INDEX, using=connection)
    a = A(
        "terms",
        field="type",
        missing="unknown",
        size=200,
    )
    a.metric("cited_by_sum", "sum", field="cited_by_count")
    s.aggs.bucket("groupby", a)
    response = s.execute()
    buckets = response.aggregations.groupby.buckets

    hits = []
    for b in buckets:
        if b.key.startswith(q):
            hits.append(
                OrderedDict(
                    {
                        "id": None,
                        "display_name": b.key,
                        "cited_by_count": b.cited_by_sum.value,
                        "entity_type": "institution",
                        "external_id": None,
                    }
                )
            )

    result = OrderedDict()
    result["meta"] = {
        "count": len(hits),
        "db_response_time_ms": response.took,
        "page": 1,
        "per_page": 10,
    }
    result["results"] = hits
    message_schema = MessageAutocompleteCustomSchema()
    return message_schema.dump(result)
