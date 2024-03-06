from flask import Blueprint, jsonify, request

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
from source_types.fields import fields_dict
from source_types.schemas import SourceTypesSchema, MessageSchema
from settings import SOURCE_TYPES_INDEX

blueprint = Blueprint("source_types", __name__)


@blueprint.route("/source-types")
@cache.cached(
    timeout=24 * 60 * 60, query_string=True, unless=lambda: not is_cached(request)
)
def source_types():
    index_name = SOURCE_TYPES_INDEX
    default_sort = ["-works_count", "id"]
    only_fields = process_only_fields(request, SourceTypesSchema)
    result = shared_view(request, fields_dict, index_name, default_sort)
    # export option
    if is_group_by_export(request):
        return export_group_by(result, request)
    message_schema = MessageSchema(only=only_fields)
    return message_schema.dump(result)


@blueprint.route("/source-types/filters/<path:params>")
def source_types_filters(params):
    index_name = SOURCE_TYPES_INDEX
    results = shared_filter_view(request, params, fields_dict, index_name)
    filters_schema = FiltersWrapperSchema()
    return filters_schema.dump(results)


@blueprint.route("/source-types/histogram/<string:param>")
def source_types_histograms(param):
    index_name = SOURCE_TYPES_INDEX
    result = shared_histogram_view(request, param, fields_dict, index_name)
    histogram_schema = HistogramWrapperSchema()
    return histogram_schema.dump(result)


@blueprint.route("/source-types/valid_fields")
def source_types_valid_fields():
    valid_fields = get_valid_fields(fields_dict)
    return jsonify(valid_fields)


@blueprint.route("/source-types/flattened_schema")
def source_types_flattened_schema():
    flattened_schema = get_flattened_fields(SourceTypesSchema())
    return jsonify(flattened_schema)


@blueprint.route("/source-types/filters_docstrings")
def source_types_filters_doctrings():
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
