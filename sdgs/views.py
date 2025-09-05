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
from sdgs.fields import fields_dict
from sdgs.schemas import SdgsSchema, MessageSchema
from settings import SDGS_INDEX

blueprint = Blueprint("sdgs", __name__)


@blueprint.route("/sdgs")
@cache.cached(
    timeout=24 * 60 * 60, query_string=True, unless=lambda: not is_cached(request)
)
def sdgs():
    index_name = SDGS_INDEX
    data_version = request.args.get('data_version') or request.args.get('data-version', '1')
    connection = 'walden' if data_version == '2' else 'default'

    default_sort = ["-works_count", "id"]
    only_fields = process_only_fields(request, SdgsSchema)
    result = shared_view(request, fields_dict, index_name, default_sort, connection)
    # export option
    if is_group_by_export(request):
        return export_group_by(result, request)
    message_schema = MessageSchema(only=only_fields)
    return message_schema.dump(result)


@blueprint.route("/sdgs/filters/<path:params>")
def sdgs_filters(params):
    index_name = SDGS_INDEX
    results = shared_filter_view(request, params, fields_dict, index_name)
    filters_schema = FiltersWrapperSchema()
    return filters_schema.dump(results)


@blueprint.route("/sdgs/histogram/<string:param>")
def sdgs_histograms(param):
    index_name = SDGS_INDEX
    result = shared_histogram_view(request, param, fields_dict, index_name)
    histogram_schema = HistogramWrapperSchema()
    return histogram_schema.dump(result)


@blueprint.route("/sdgs/valid_fields")
def sdgs_valid_fields():
    valid_fields = get_valid_fields(fields_dict)
    return jsonify(valid_fields)


@blueprint.route("/sdgs/flattened_schema")
def sdgs_flattened_schema():
    flattened_schema = get_flattened_fields(SdgsSchema())
    return jsonify(flattened_schema)


@blueprint.route("/sdgs/filters_docstrings")
def sdgs_filters_doctrings():
    ret = {}
    for param, f in fields_dict.items():
        ret[param] = {
            "key": f.param,
            "entityType": "sdgs",
            "docstring": f.docstring,
            "documentationLink": f.documentation_link,
            "alternateNames": f.alternate_names,
        }
    return jsonify(ret)


@blueprint.route("/sdgs/config")
def sdgs_config():
    return jsonify(all_entities_config["sdgs"])
