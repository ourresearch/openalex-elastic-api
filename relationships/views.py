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
from relationships.fields import fields_dict
from relationships.schemas import RelationshipsSchema, MessageSchema
from settings import WORK_RELATIONSHIPS_INDEX

# oxjob #2065: the kinds of link between a work and its parent work (volume, component,
# data-series, part). `/work-relationships` is an alias, as `/work-types` is for `/types`.
blueprint = Blueprint("relationships", __name__)


@blueprint.route("/relationships")
@blueprint.route("/work-relationships")
@blueprint.route("/entities/relationships")
def relationships():
    index_name = WORK_RELATIONSHIPS_INDEX
    default_sort = ["-works_count", "id"]
    only_fields = process_only_fields(request, RelationshipsSchema)
    result = shared_view(request, fields_dict, index_name, default_sort)
    # export option
    if is_group_by_export(request):
        return export_group_by(result, request)
    message_schema = MessageSchema(only=only_fields)
    return message_schema.dump(result)


@blueprint.route("/relationships/filters/<path:params>")
@blueprint.route("/work-relationships/filters/<path:params>")
def relationships_filters(params):
    index_name = WORK_RELATIONSHIPS_INDEX
    results = shared_filter_view(request, params, fields_dict, index_name)
    filters_schema = FiltersWrapperSchema()
    return filters_schema.dump(results)


@blueprint.route("/relationships/histogram/<string:param>")
@blueprint.route("/work-relationships/histogram/<string:param>")
def relationships_histograms(param):
    index_name = WORK_RELATIONSHIPS_INDEX
    result = shared_histogram_view(request, param, fields_dict, index_name)
    histogram_schema = HistogramWrapperSchema()
    return histogram_schema.dump(result)


@blueprint.route("/relationships/valid_fields")
@blueprint.route("/work-relationships/valid_fields")
def relationships_valid_fields():
    valid_fields = get_valid_fields(fields_dict)
    return jsonify(valid_fields)


@blueprint.route("/relationships/flattened_schema")
@blueprint.route("/work-relationships/flattened_schema")
def relationships_flattened_schema():
    flattened_schema = get_flattened_fields(RelationshipsSchema())
    return jsonify(flattened_schema)


@blueprint.route("/relationships/filters_docstrings")
@blueprint.route("/work-relationships/filters_docstrings")
def relationships_filters_doctrings():
    ret = {}
    for param, f in fields_dict.items():
        ret[param] = {
            "key": f.param,
            "entityType": "relationships",
            "docstring": f.docstring,
            "documentationLink": f.documentation_link,
            "alternateNames": f.alternate_names,
        }
    return jsonify(ret)


@blueprint.route("/relationships/config")
@blueprint.route("/work-relationships/config")
def relationships_config():
    return jsonify(all_entities_config["relationships"])
