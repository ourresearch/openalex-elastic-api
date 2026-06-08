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
from oa_statuses.fields import fields_dict
from oa_statuses.schemas import OaStatusesSchema, MessageSchema
from settings import OA_STATUSES_INDEX

blueprint = Blueprint("oa_statuses", __name__)


@blueprint.route("/oa-statuses")
@blueprint.route("/entities/oa-statuses")
def oa_statuses():
    index_name = OA_STATUSES_INDEX
    default_sort = ["-works_count", "id"]
    only_fields = process_only_fields(request, OaStatusesSchema)
    result = shared_view(request, fields_dict, index_name, default_sort)
    # export option
    if is_group_by_export(request):
        return export_group_by(result, request)
    message_schema = MessageSchema(only=only_fields)
    return message_schema.dump(result)


@blueprint.route("/oa-statuses/filters/<path:params>")
def oa_statuses_filters(params):
    index_name = OA_STATUSES_INDEX
    results = shared_filter_view(request, params, fields_dict, index_name)
    filters_schema = FiltersWrapperSchema()
    return filters_schema.dump(results)


@blueprint.route("/oa-statuses/histogram/<string:param>")
def oa_statuses_histograms(param):
    index_name = OA_STATUSES_INDEX
    result = shared_histogram_view(request, param, fields_dict, index_name)
    histogram_schema = HistogramWrapperSchema()
    return histogram_schema.dump(result)


@blueprint.route("/oa-statuses/valid_fields")
def oa_statuses_valid_fields():
    valid_fields = get_valid_fields(fields_dict)
    return jsonify(valid_fields)


@blueprint.route("/oa-statuses/flattened_schema")
def oa_statuses_flattened_schema():
    flattened_schema = get_flattened_fields(OaStatusesSchema())
    return jsonify(flattened_schema)


@blueprint.route("/oa-statuses/filters_docstrings")
def oa_statuses_filters_doctrings():
    ret = {}
    for param, f in fields_dict.items():
        ret[param] = {
            "key": f.param,
            "entityType": "oa-statuses",
            "docstring": f.docstring,
            "documentationLink": f.documentation_link,
            "alternateNames": f.alternate_names,
        }
    return jsonify(ret)


@blueprint.route("/oa-statuses/config")
def oa_statuses_config():
    return jsonify(all_entities_config["oa-statuses"])
