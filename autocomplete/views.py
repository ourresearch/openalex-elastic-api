from collections import OrderedDict

import iso3166
from elasticsearch_dsl import Search
from flask import Blueprint, request

from autocomplete.schemas import MessageAutocompleteCustomSchema, MessageSchema
from autocomplete.shared import single_entity_autocomplete
from autocomplete.utils import strip_punctuation
from core.exceptions import APIQueryParamsError

blueprint = Blueprint("complete", __name__)


@blueprint.route("/autocomplete")
def autocomplete_full():
    entities_to_indeces = {
        "author": "authors-v6",
        "concept": "concepts-v3",
        "institution": "institutions-v3",
        "venue": "venues-v4",
        "work": "works-v8-*,-*invalid-data",
    }

    q = request.args.get("q")
    q = strip_punctuation(q) if q else None
    entity_type = request.args.get("entity_type")

    if not q:
        raise APIQueryParamsError(
            f"Must enter a 'q' parameter in order to use autocomplete. Example: {request.url_rule}?q=my search"
        )

    if entity_type and not q:
        raise APIQueryParamsError(
            f"Must provide a 'q' parameter when filtering by an entity type."
        )

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
    s = s.query("match_phrase_prefix", display_name__autocomplete=q)
    s = s.sort("-cited_by_count")
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
    return message_schema.dump(result)


@blueprint.route("/autocomplete/authors")
def autocomplete_authors():
    index_name = "authors-v6"
    result = single_entity_autocomplete(index_name, request)
    message_schema = MessageSchema()
    return message_schema.dump(result)


@blueprint.route("/autocomplete/concepts")
def autocomplete_concepts():
    index_name = "concepts-v3"
    result = single_entity_autocomplete(index_name, request)
    message_schema = MessageSchema()
    return message_schema.dump(result)


@blueprint.route("/autocomplete/institutions")
def autocomplete_institutions():
    index_name = "institutions-v3"
    result = single_entity_autocomplete(index_name, request)
    message_schema = MessageSchema()
    return message_schema.dump(result)


@blueprint.route("/autocomplete/venues")
def autocomplete_venues():
    index_name = "venues-v4"
    result = single_entity_autocomplete(index_name, request)
    message_schema = MessageSchema()
    return message_schema.dump(result)


@blueprint.route("/autocomplete/works")
def autocomplete_works():
    index_name = "works-v8-*,-*invalid-data"
    result = single_entity_autocomplete(index_name, request)
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
