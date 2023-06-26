from flask import Blueprint, jsonify, request

from core.export import export_group_by, is_group_by_export
from core.filters_view import shared_filter_view
from core.schemas import FiltersWrapperSchema, StatsWrapperSchema
from core.shared_view import shared_view
from core.stats_view import shared_stats_view
from core.utils import (get_flattened_fields, get_valid_fields, is_cached,
                        process_only_fields)
from extensions import cache
from settings import WORKS_INDEX
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
@cache.cached(
    timeout=24 * 60 * 60, query_string=True, unless=lambda: not is_cached(request)
)
def works():
    index_name = WORKS_INDEX
    default_sort = ["-cited_by_count", "id"]
    only_fields = process_only_fields(request, WorksSchema)
    result = shared_view(request, fields_dict, index_name, default_sort)
    # export option
    if is_group_by_export(request):
        return export_group_by(result, request)
    message_schema = MessageSchema(only=only_fields)
    return message_schema.dump(result)


@blueprint.route("/works/filters/<path:params>")
def works_filters(params):
    index_name = WORKS_INDEX
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
    index_name = WORKS_INDEX
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
