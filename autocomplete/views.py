from collections import OrderedDict

import iso3166
from elasticsearch_dsl import A, Search
from flask import Blueprint, request, jsonify

from authors.fields import fields_dict as authors_fields_dict
from autocomplete.schemas import MessageAutocompleteCustomSchema, MessageSchema
from autocomplete.shared import (
    search_canonical_id_full,
    single_entity_autocomplete,
)
from autocomplete.utils import (
    AUTOCOMPLETE_SOURCE,
    is_cached_autocomplete,
    strip_punctuation,
)
from autocomplete.full import (
    get_indices_and_boosts,
    get_filter_results,
    build_full_search_query,
)
from autocomplete.validate import validate_full_autocomplete_params
from concepts.fields import fields_dict as concepts_fields_dict
from core.exceptions import APIQueryParamsError
from core.utils import clean_preference
from extensions import cache
from funders.fields import fields_dict as funders_fields_dict
from institutions.fields import fields_dict as institutions_fields_dict
from publishers.fields import fields_dict as publishers_fields_dict
from settings import (
    AUTHORS_INDEX,
    CONCEPTS_INDEX,
    FUNDERS_INDEX,
    INSTITUTIONS_INDEX,
    PUBLISHERS_INDEX,
    SOURCES_INDEX,
    VENUES_INDEX,
    WORKS_INDEX,
)
from sources.fields import fields_dict as sources_fields_dict
from venues.fields import fields_dict as venues_fields_dict
from works.fields import fields_dict as works_fields_dict

blueprint = Blueprint("complete", __name__)


@blueprint.route("/autocomplete")
@cache.cached(
    timeout=24 * 60 * 60 * 7,
    query_string=True,
    unless=lambda: not is_cached_autocomplete(request),
)
def autocomplete_full():
    validate_full_autocomplete_params(request)
    q = request.args.get("q")
    hide_works = request.args.get("hide_works")
    entity_type = request.args.get("entity_type")
    filter_results = []

    entities_to_indeces, index_boosts = get_indices_and_boosts()
    if hide_works:
        entities_to_indeces.pop("work")

    if entity_type:
        try:
            index = entities_to_indeces[entity_type]
        except KeyError:
            raise APIQueryParamsError(
                f"{entity_type} is not a valid value for parameter entity_type. Valid entity_type values are: {', '.join(entities_to_indeces.keys())}."
            )
    else:
        index = ",".join(entities_to_indeces.values())

    s = Search(index=index)

    if q:
        # canonical id match
        s, canonical_id_found = search_canonical_id_full(s, q)
        if not canonical_id_found:
            s = build_full_search_query(q, s)
            filter_results = get_filter_results(q)

    s = s.source(AUTOCOMPLETE_SOURCE)
    preference = clean_preference(q)
    s = s.extra(indices_boost=index_boosts)
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
    author_hint = request.args.get("author_hint")
    if author_hint:
        message_schema.context["author_hint"] = author_hint
    results = message_schema.dump(result)
    if filter_results:
        max_results_count = 10 - len(filter_results)

        # remove excess results from the end of the list
        results["results"] = results["results"][:max_results_count]

        # insert the filter_results at the beginning of the list
        results["results"] = filter_results + results["results"]
    return results


@blueprint.route("/autocomplete/authors")
@cache.cached(
    timeout=24 * 60 * 60 * 7,
    query_string=True,
    unless=lambda: not is_cached_autocomplete(request),
)
def autocomplete_authors():
    author_hint = request.args.get("author_hint")
    index_name = AUTHORS_INDEX
    result = single_entity_autocomplete(authors_fields_dict, index_name, request)
    message_schema = MessageSchema()
    if author_hint:
        message_schema.context["author_hint"] = author_hint
    return message_schema.dump(result)


@blueprint.route("/autocomplete/concepts")
def autocomplete_concepts():
    index_name = CONCEPTS_INDEX
    result = single_entity_autocomplete(concepts_fields_dict, index_name, request)
    message_schema = MessageSchema()
    return message_schema.dump(result)


@blueprint.route("/autocomplete/funders")
def autocomplete_funders():
    index_name = FUNDERS_INDEX
    result = single_entity_autocomplete(funders_fields_dict, index_name, request)
    message_schema = MessageSchema()
    return message_schema.dump(result)


@blueprint.route("/autocomplete/institutions")
def autocomplete_institutions():
    index_name = INSTITUTIONS_INDEX
    result = single_entity_autocomplete(institutions_fields_dict, index_name, request)
    message_schema = MessageSchema()
    return message_schema.dump(result)


@blueprint.route("/autocomplete/venues")
def autocomplete_venues():
    index_name = VENUES_INDEX
    result = single_entity_autocomplete(venues_fields_dict, index_name, request)
    message_schema = MessageSchema()
    return message_schema.dump(result)


@blueprint.route("/autocomplete/works")
@cache.cached(
    timeout=24 * 60 * 60 * 7,
    query_string=True,
    unless=lambda: not is_cached_autocomplete(request),
)
def autocomplete_works():
    index_name = WORKS_INDEX
    result = single_entity_autocomplete(works_fields_dict, index_name, request)
    message_schema = MessageSchema()
    return message_schema.dump(result)


@blueprint.route("/autocomplete/publishers")
def autocomplete_publishers():
    index_name = PUBLISHERS_INDEX
    result = single_entity_autocomplete(publishers_fields_dict, index_name, request)
    message_schema = MessageSchema()
    return message_schema.dump(result)


@blueprint.route("/autocomplete/sources")
def autocomplete_sources():
    index_name = SOURCES_INDEX
    result = single_entity_autocomplete(sources_fields_dict, index_name, request)
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

    # get countries and citation sums from elastic transform
    s = Search(index="institutions-countries-transform-v1").extra(size=500)
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


@blueprint.route("/autocomplete/venues/publisher")
def autocomplete_venues_publisher():
    q = request.args.get("q")
    q = strip_punctuation(q) if q else None
    q = q.lower() if q else None
    if not q:
        raise APIQueryParamsError(
            f"Must enter a 'q' parameter in order to use autocomplete. Example: {request.url_rule}?q=my search"
        )

    s = Search(index="venues-publisher-transform-v2")
    s = s.query(
        "match_phrase_prefix", publisher__transform={"query": q, "max_expansions": 100}
    )
    s = s.sort("-cited_by_count.sum")
    response = s.execute()

    hits = []
    for item in response:
        hits.append(
            OrderedDict(
                {
                    "id": None,
                    "display_name": item.publisher.transform,
                    "cited_by_count": item.cited_by_count.sum,
                    "entity_type": "venue",
                    "external_id": None,
                }
            )
        )

    result = OrderedDict()
    result["meta"] = {
        "count": s.count(),
        "db_response_time_ms": response.took,
        "page": 1,
        "per_page": 10,
    }
    result["results"] = hits
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

    s = Search(index=INSTITUTIONS_INDEX)
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
