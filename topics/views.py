from flask import Blueprint, jsonify, request, abort

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
from topics.fields import fields_dict
from topics.schemas import TopicsSchema, MessageSchema
from settings import TOPICS_INDEX

blueprint = Blueprint("topics", __name__)


@blueprint.route("/topics")
@blueprint.route("/entities/topics")
def topics():
    index_name = TOPICS_INDEX
    default_sort = ["-works_count", "id"]
    only_fields = process_only_fields(request, TopicsSchema)
    result = shared_view(request, fields_dict, index_name, default_sort)
    # export option
    if is_group_by_export(request):
        return export_group_by(result, request)
    message_schema = MessageSchema(only=only_fields)
    return message_schema.dump(result)


@blueprint.route("/topics/filters/<path:params>")
def topics_filters(params):
    index_name = TOPICS_INDEX
    results = shared_filter_view(request, params, fields_dict, index_name)
    filters_schema = FiltersWrapperSchema()
    return filters_schema.dump(results)


@blueprint.route("/topics/histogram/<string:param>")
def topics_histograms(param):
    index_name = TOPICS_INDEX
    result = shared_histogram_view(request, param, fields_dict, index_name)
    histogram_schema = HistogramWrapperSchema()
    return histogram_schema.dump(result)


@blueprint.route("/topics/valid_fields")
def topics_valid_fields():
    valid_fields = get_valid_fields(fields_dict)
    return jsonify(valid_fields)


@blueprint.route("/topics/flattened_schema")
def topics_flattened_schema():
    flattened_schema = get_flattened_fields(TopicsSchema())
    return jsonify(flattened_schema)


@blueprint.route("/topics/filters_docstrings")
def topics_filters_doctrings():
    ret = {}
    for param, f in fields_dict.items():
        ret[param] = {
            "key": f.param,
            "entityType": "topics",
            "docstring": f.docstring,
            "documentationLink": f.documentation_link,
            "alternateNames": f.alternate_names,
        }
    return jsonify(ret)


@blueprint.route("/topics/config")
def topics_config():
    return jsonify(all_entities_config["topics"])
