from flask import Blueprint, jsonify, request

from config.entity_config import entity_configs_dict
from config.property_config import property_configs_dict
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
from licenses.fields import fields_dict
from licenses.schemas import LicensesSchema, MessageSchema
from settings import LICENSES_INDEX

blueprint = Blueprint("licenses", __name__)


@blueprint.route("/licenses")
@cache.cached(
    timeout=24 * 60 * 60, query_string=True, unless=lambda: not is_cached(request)
)
def licenses():
    index_name = LICENSES_INDEX
    default_sort = ["-works_count", "id"]
    only_fields = process_only_fields(request, LicensesSchema)
    result = shared_view(request, fields_dict, index_name, default_sort)
    # export option
    if is_group_by_export(request):
        return export_group_by(result, request)
    message_schema = MessageSchema(only=only_fields)
    return message_schema.dump(result)


@blueprint.route("/licenses/filters/<path:params>")
def licenses_filters(params):
    index_name = LICENSES_INDEX
    results = shared_filter_view(request, params, fields_dict, index_name)
    filters_schema = FiltersWrapperSchema()
    return filters_schema.dump(results)


@blueprint.route("/licenses/histogram/<string:param>")
def licenses_histograms(param):
    index_name = LICENSES_INDEX
    result = shared_histogram_view(request, param, fields_dict, index_name)
    histogram_schema = HistogramWrapperSchema()
    return histogram_schema.dump(result)


@blueprint.route("/licenses/valid_fields")
def licenses_valid_fields():
    valid_fields = get_valid_fields(fields_dict)
    return jsonify(valid_fields)


@blueprint.route("/licenses/flattened_schema")
def licenses_flattened_schema():
    flattened_schema = get_flattened_fields(LicensesSchema())
    return jsonify(flattened_schema)


@blueprint.route("/licenses/filters_docstrings")
def licenses_filters_doctrings():
    ret = {}
    for param, f in fields_dict.items():
        ret[param] = {
            "key": f.param,
            "entityType": "licenses",
            "docstring": f.docstring,
            "documentationLink": f.documentation_link,
            "alternateNames": f.alternate_names,
        }
    return jsonify(ret)


@blueprint.route("/licenses/config")
def licenses_config():
    result = entity_configs_dict["licenses"]
    result["properties"] = property_configs_dict["licenses"]
    return jsonify(result)
