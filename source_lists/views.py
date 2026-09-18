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
    process_only_fields,
)
from source_lists.fields import fields_dict
from source_lists.schemas import SourceListsSchema, MessageSchema
from settings import SOURCE_LISTS_INDEX

blueprint = Blueprint("source_lists", __name__)


@blueprint.route("/source-lists")
@blueprint.route("/entities/source-lists")
def source_lists():
    index_name = SOURCE_LISTS_INDEX
    default_sort = ["-works_count", "id"]
    only_fields = process_only_fields(request, SourceListsSchema)
    result = shared_view(request, fields_dict, index_name, default_sort)
    # export option
    if is_group_by_export(request):
        return export_group_by(result, request)
    message_schema = MessageSchema(only=only_fields)
    return message_schema.dump(result)


@blueprint.route("/source-lists/filters/<path:params>")
def source_lists_filters(params):
    index_name = SOURCE_LISTS_INDEX
    results = shared_filter_view(request, params, fields_dict, index_name)
    filters_schema = FiltersWrapperSchema()
    return filters_schema.dump(results)


@blueprint.route("/source-lists/histogram/<string:param>")
def source_lists_histograms(param):
    index_name = SOURCE_LISTS_INDEX
    result = shared_histogram_view(request, param, fields_dict, index_name)
    histogram_schema = HistogramWrapperSchema()
    return histogram_schema.dump(result)


@blueprint.route("/source-lists/valid_fields")
def source_lists_valid_fields():
    valid_fields = get_valid_fields(fields_dict)
    return jsonify(valid_fields)


@blueprint.route("/source-lists/flattened_schema")
def source_lists_flattened_schema():
    flattened_schema = get_flattened_fields(SourceListsSchema())
    return jsonify(flattened_schema)


@blueprint.route("/source-lists/filters_docstrings")
def source_lists_filters_doctrings():
    ret = {}
    for param, f in fields_dict.items():
        ret[param] = {
            "key": f.param,
            "entityType": "source-lists",
            "docstring": f.docstring,
            "documentationLink": f.documentation_link,
            "alternateNames": f.alternate_names,
        }
    return jsonify(ret)


@blueprint.route("/source-lists/config")
def source_lists_config():
    return jsonify(all_entities_config["source-lists"])
