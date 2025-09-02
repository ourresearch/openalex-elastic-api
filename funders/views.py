from flask import Blueprint, jsonify, request, abort

from combined_config import all_entities_config
from core.export import export_group_by, is_group_by_export
from core.filters_view import shared_filter_view
from core.histogram import shared_histogram_view
from core.schemas import FiltersWrapperSchema, HistogramWrapperSchema
from core.shared_view import shared_view
from core.utils import (get_flattened_fields, get_valid_fields, is_cached,
                        process_only_fields)
from extensions import cache
from funders.fields import fields_dict
from funders.schemas import FundersSchema, MessageSchema
from settings import FUNDERS_INDEX

blueprint = Blueprint("funders", __name__)


@blueprint.route("/funders")
@cache.cached(
    timeout=24 * 60 * 60, query_string=True, unless=lambda: not is_cached(request)
)
def funders():
    data_version = request.args.get('data_version') or request.args.get('data-version', '1')
    if data_version == '2':
        abort(404)
    
    index_name = FUNDERS_INDEX
    default_sort = ["-works_count", "id"]
    only_fields = process_only_fields(request, FundersSchema)
    result = shared_view(request, fields_dict, index_name, default_sort)
    # export option
    if is_group_by_export(request):
        return export_group_by(result, request)
    message_schema = MessageSchema(only=only_fields)
    return message_schema.dump(result)


@blueprint.route("/funders/filters/<path:params>")
def funders_filters(params):
    index_name = FUNDERS_INDEX
    results = shared_filter_view(request, params, fields_dict, index_name)
    filters_schema = FiltersWrapperSchema()
    return filters_schema.dump(results)


@blueprint.route("/funders/histogram/<string:param>")
def funders_histograms(param):
    index_name = FUNDERS_INDEX
    result = shared_histogram_view(request, param, fields_dict, index_name)
    histogram_schema = HistogramWrapperSchema()
    return histogram_schema.dump(result)


@blueprint.route("/funders/valid_fields")
def funders_valid_fields():
    valid_fields = get_valid_fields(fields_dict)
    return jsonify(valid_fields)


@blueprint.route("/funders/flattened_schema")
def funders_flattened_schema():
    flattened_schema = get_flattened_fields(FundersSchema())
    return jsonify(flattened_schema)


@blueprint.route("/funders/filters_docstrings")
def funders_filters_doctrings():
    ret = {}
    for param, f in fields_dict.items():
        ret[param] = {
            "key": f.param,
            "entityType": "funders",
            "docstring": f.docstring,
            "documentationLink": f.documentation_link,
            "alternateNames": f.alternate_names,
        }
    return jsonify(ret)


@blueprint.route("/funders/config")
def funders_config():
    return jsonify(all_entities_config["funders"])
