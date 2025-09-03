from flask import Blueprint, jsonify, request

from combined_config import all_entities_config
from core.export import export_group_by, is_group_by_export
from core.filters_view import shared_filter_view
from core.histogram import shared_histogram_view
from core.schemas import FiltersWrapperSchema, HistogramWrapperSchema
from core.shared_view import shared_view
from core.utils import (
    get_flattened_fields,
    get_valid_fields,
    is_cached,
    process_only_fields,
)
from extensions import cache
from work_types.fields import fields_dict
from work_types.schemas import TypesSchema, MessageSchema
from settings import WORK_TYPES_INDEX

blueprint = Blueprint("types", __name__)


@blueprint.route("/types")
@blueprint.route("/work-types")
@cache.cached(
    timeout=24 * 60 * 60, query_string=True, unless=lambda: not is_cached(request)
)
def types():
    default_sort = ["-works_count", "id"]
    only_fields = process_only_fields(request, TypesSchema)
    
    # Check data_version parameter to determine connection and index
    data_version = request.args.get('data_version') or request.args.get('data-version', '1')
    connection = 'walden' if data_version == '2' else 'default'
    
    result = shared_view(request, fields_dict, WORK_TYPES_INDEX, default_sort, connection)
    # export option
    if is_group_by_export(request):
        return export_group_by(result, request)
    message_schema = MessageSchema(only=only_fields)
    return message_schema.dump(result)


@blueprint.route("/types/filters/<path:params>")
@blueprint.route("/work-types/filters/<path:params>")
def types_filters(params):
    index_name = WORK_TYPES_INDEX
    results = shared_filter_view(request, params, fields_dict, index_name)
    filters_schema = FiltersWrapperSchema()
    return filters_schema.dump(results)


@blueprint.route("/types/histogram/<string:param>")
@blueprint.route("/work-types/histogram/<string:param>")
def types_histograms(param):
    index_name = WORK_TYPES_INDEX
    result = shared_histogram_view(request, param, fields_dict, index_name)
    histogram_schema = HistogramWrapperSchema()
    return histogram_schema.dump(result)


@blueprint.route("/types/valid_fields")
@blueprint.route("/work-types/valid_fields")
def types_valid_fields():
    valid_fields = get_valid_fields(fields_dict)
    return jsonify(valid_fields)


@blueprint.route("/types/flattened_schema")
@blueprint.route("/work-types/flattened_schema")
def types_flattened_schema():
    flattened_schema = get_flattened_fields(TypesSchema())
    return jsonify(flattened_schema)


@blueprint.route("/types/filters_docstrings")
@blueprint.route("/work-types/filters_docstrings")
def types_filters_doctrings():
    ret = {}
    for param, f in fields_dict.items():
        ret[param] = {
            "key": f.param,
            "entityType": "types",
            "docstring": f.docstring,
            "documentationLink": f.documentation_link,
            "alternateNames": f.alternate_names,
        }
    return jsonify(ret)


@blueprint.route("/v2/work-types")
def v2_work_types():
    index_name = "work-types-v1"
    default_sort = ["id"]
    only_fields = process_only_fields(request, TypesSchema)
    result = shared_view(request, fields_dict, index_name, default_sort, connection='v2')
    message_schema = MessageSchema(only=only_fields)
    return message_schema.dump(result)


@blueprint.route("/types/config")
@blueprint.route("/work-types/config")
def types_config():
    return jsonify(all_entities_config["types"])
