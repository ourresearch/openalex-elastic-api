from flask import Blueprint, jsonify, request

from core.export import export_group_by, is_group_by_export
from core.filters_view import shared_filter_view
from core.schemas import FiltersWrapperSchema
from core.shared_view import shared_view
from core.utils import get_valid_fields, is_cached, process_only_fields, get_flattened_fields
from extensions import cache
from settings import SOURCES_INDEX
from sources.fields import fields_dict
from sources.schemas import MessageSchema, SourcesSchema

blueprint = Blueprint("sources", __name__)


@blueprint.route("/sources")
@blueprint.route("/journals", endpoint="journals_view")
@cache.cached(
    timeout=24 * 60 * 60, query_string=True, unless=lambda: not is_cached(request)
)
def sources():
    index_name = SOURCES_INDEX
    default_sort = ["-works_count", "id"]
    only_fields = process_only_fields(request, SourcesSchema)
    result = shared_view(request, fields_dict, index_name, default_sort)
    # export option
    if is_group_by_export(request):
        return export_group_by(result, request)
    message_schema = MessageSchema(only=only_fields)
    return message_schema.dump(result)


@blueprint.route("/sources/filters/<path:params>")
@blueprint.route("/journals/filters/<path:params>", endpoint="journals_filter_view")
def sources_filters(params):
    index_name = SOURCES_INDEX
    results = shared_filter_view(request, params, fields_dict, index_name)
    filters_schema = FiltersWrapperSchema()
    return filters_schema.dump(results)


@blueprint.route("/sources/valid_fields")
def sources_valid_fields():
    valid_fields = get_valid_fields(fields_dict)
    return jsonify(valid_fields)


@blueprint.route("/sources/flattened_schema")
def sources_flattened_schema():
    flattened_schema = get_flattened_fields(SourcesSchema())
    return jsonify(flattened_schema)
