from collections import OrderedDict

from elasticsearch_dsl import Search
from flask import Blueprint, request

from autocomplete.schemas import MessageSchema
from autocomplete.shared import single_entity_autocomplete
from core.exceptions import APIQueryParamsError

blueprint = Blueprint("complete", __name__)


@blueprint.route("/autocomplete")
def autocomplete_full():
    entities_to_indeces = {
        "author": "authors-v5",
        "concept": "concepts-v2",
        "institution": "institutions-v2",
        "venue": "venues-v3",
        "work": "works-v7-*,-*invalid-data",
    }

    q = request.args.get("q")
    entity_type = request.args.get("entity_type")

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
    index_name = "authors-v5"
    result = single_entity_autocomplete(index_name, request)
    message_schema = MessageSchema()
    return message_schema.dump(result)


@blueprint.route("/autocomplete/concepts")
def autocomplete_concepts():
    index_name = "concepts-v2"
    result = single_entity_autocomplete(index_name, request)
    message_schema = MessageSchema()
    return message_schema.dump(result)


@blueprint.route("/autocomplete/institutions")
def autocomplete_institutions():
    index_name = "institutions-v2"
    result = single_entity_autocomplete(index_name, request)
    message_schema = MessageSchema()
    return message_schema.dump(result)


@blueprint.route("/autocomplete/venues")
def autocomplete_venues():
    index_name = "venues-v3"
    result = single_entity_autocomplete(index_name, request)
    message_schema = MessageSchema()
    return message_schema.dump(result)


@blueprint.route("/autocomplete/works")
def autocomplete_works():
    index_name = "works-v7-*,-*invalid-data"
    result = single_entity_autocomplete(index_name, request)
    message_schema = MessageSchema()
    return message_schema.dump(result)
