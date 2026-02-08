from flask import Blueprint, jsonify, request

from combined_config import all_entities_config
from core.export import export_group_by, is_group_by_export
from core.filters_view import shared_filter_view
from core.semantic import semantic_search
from core.schemas import FiltersWrapperSchema, StatsWrapperSchema
from core.shared_view import shared_view
from core.stats_view import shared_stats_view
from core.utils import (get_data_version_connection, get_entity_counts,
                        get_flattened_fields, get_valid_fields, process_only_fields)
from settings import WORKS_INDEX_LEGACY, WORKS_INDEX_WALDEN
from works.fields import fields_dict
from works.schemas import MessageSchema, WorksSchema

blueprint = Blueprint("works", __name__)


@blueprint.route("/")
def index():
    return jsonify(
        {
            "version": "0.1",
            "documentation_url": "/docs",
            "msg": "Don't panic",
        }
    )


@blueprint.route("/works")
@blueprint.route("/entities/works")
def works():
    """
    List and search works.

    Supports multiple search modes via dot notation:
        GET /works?search=machine+learning                    (text search)
        GET /works?search.semantic=machine+learning            (vector search)
        GET /works?search.semantic=climate+change&filter=is_oa:true  (vector + filters)
    """
    default_sort = ["-cited_by_percentile_year.max", "-cited_by_count", "id"]
    only_fields = process_only_fields(request, WorksSchema)

    connection = get_data_version_connection(request)
    index_name = WORKS_INDEX_WALDEN if connection == 'walden' else WORKS_INDEX_LEGACY

    default_filters = None
    if connection == 'walden':
        current_filter = request.args.get('filter', '')
        include_xpac = request.args.get('include_xpac') == 'true' or request.args.get('include-xpac') == 'true'

        if 'is_xpac:' not in current_filter and 'is-xpac:' not in current_filter and not include_xpac:
            default_filters = [{'is_xpac': 'false'}]

    result = shared_view(request, fields_dict, index_name, default_sort, connection, default_filters=default_filters)
    if is_group_by_export(request):
        return export_group_by(result, request)
    message_schema = MessageSchema(only=only_fields)
    return message_schema.dump(result)


@blueprint.route("/v2/works")
def v2_works():
    index_name = WORKS_INDEX_WALDEN
    default_sort = ["-cited_by_percentile_year.max", "-cited_by_count", "id"]
    only_fields = process_only_fields(request, WorksSchema)
    result = shared_view(request, fields_dict, index_name, default_sort, connection='walden')
    message_schema = MessageSchema(only=only_fields)
    return message_schema.dump(result)


@blueprint.route("/works/filters/<path:params>")
def works_filters(params):
    index_name = WORKS_INDEX_LEGACY
    results = shared_filter_view(request, params, fields_dict, index_name)
    filters_schema = FiltersWrapperSchema()
    return filters_schema.dump(results)


@blueprint.route("/works/stats/")
def works_stats():
    stats_fields = [
        "apc_payment.price_usd",
        "authors_count",
        "cited_by_count",
        "referenced_works_count",
    ]
    index_name = WORKS_INDEX_LEGACY
    entity_name = "works"
    result = shared_stats_view(
        request, fields_dict, index_name, stats_fields, entity_name
    )
    stats_schema = StatsWrapperSchema()
    return stats_schema.dump(result)


@blueprint.route("/works/valid_fields")
def works_valid_fields():
    valid_fields = get_valid_fields(fields_dict)
    return jsonify(valid_fields)


@blueprint.route("/works/flattened_schema")
def works_flattened_schema():
    flattened_schema = get_flattened_fields(WorksSchema())
    return jsonify(flattened_schema)


@blueprint.route("/works/filters_docstrings")
def works_filters_doctrings():
    ret = {}
    for param, f in fields_dict.items():
        ret[param] = {
            "key": f.param,
            "entityType": "works",
            "docstring": f.docstring,
            "documentationLink": f.documentation_link,
            "alternateNames": f.alternate_names,
        }
    return jsonify(ret)


@blueprint.route("/works/semantic")
def works_semantic():
    text = request.args.get("q")
    response = semantic_search(text)
    return jsonify(
        response
    )


@blueprint.route("/works/config")
def works_config():
    return jsonify(all_entities_config["works"])


@blueprint.route("/entities")
def entities():
    """
    Returns a list of all entity types with their name, description, and count.
    """
    # Get counts from Elasticsearch using shared function
    es_counts = get_entity_counts(request)

    entities_list = []

    # Define entity types we want to include (in order)
    entity_types = [
        "works",
        "authors",
        "sources",
        "institutions",
        "topics",
        "publishers",
        "funders",
        "domains",
        "fields",
        "subfields",
        "concepts",
        "keywords",
        "continents",
        "countries",
        "institution-types",
        "languages",
        "licenses",
        "sdgs",
        "source-types",
        "work-types",
    ]

    for entity_type in entity_types:
        if entity_type in all_entities_config:
            config = all_entities_config[entity_type]

            # Extract the relevant information
            entity_info = {
                "id": config.get("id", entity_type),
                "display_name": config.get("displayName", entity_type),
                "description": config.get("descrFull", config.get("descr", "")),
            }

            # Map entity_type to the key used in es_counts
            # (e.g., "sdgs" -> "sustainable_development_goals")
            es_key = entity_type
            if entity_type == "sdgs":
                es_key = "sustainable_development_goals"

            # Get count from Elasticsearch if available, otherwise from config values
            if es_key in es_counts:
                entity_info["count"] = es_counts[es_key]
            elif "values" in config and isinstance(config["values"], list):
                entity_info["count"] = len(config["values"])
            else:
                entity_info["count"] = None

            entities_list.append(entity_info)

    return jsonify({
        "meta": {
            "count": len(entities_list)
        },
        "results": entities_list
    })
