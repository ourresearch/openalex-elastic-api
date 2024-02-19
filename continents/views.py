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
from continents.fields import fields_dict
from continents.schemas import ContinentsSchema, MessageSchema
from settings import CONTINENTS_INDEX

blueprint = Blueprint("continents", __name__)


@blueprint.route("/continents")
@cache.cached(
    timeout=24 * 60 * 60, query_string=True, unless=lambda: not is_cached(request)
)
def continents():
    index_name = CONTINENTS_INDEX
    default_sort = ["-works_count", "id"]
    only_fields = process_only_fields(request, ContinentsSchema)
    result = shared_view(request, fields_dict, index_name, default_sort)
    # export option
    if is_group_by_export(request):
        return export_group_by(result, request)
    message_schema = MessageSchema(only=only_fields)
    return message_schema.dump(result)


@blueprint.route("/continents/filters/<path:params>")
def continents_filters(params):
    index_name = CONTINENTS_INDEX
    results = shared_filter_view(request, params, fields_dict, index_name)
    filters_schema = FiltersWrapperSchema()
    return filters_schema.dump(results)


@blueprint.route("/continents/histogram/<string:param>")
def continents_histograms(param):
    index_name = CONTINENTS_INDEX
    result = shared_histogram_view(request, param, fields_dict, index_name)
    histogram_schema = HistogramWrapperSchema()
    return histogram_schema.dump(result)


@blueprint.route("/continents/valid_fields")
def continents_valid_fields():
    valid_fields = get_valid_fields(fields_dict)
    return jsonify(valid_fields)


@blueprint.route("/continents/flattened_schema")
def continents_flattened_schema():
    flattened_schema = get_flattened_fields(ContinentsSchema())
    return jsonify(flattened_schema)


@blueprint.route("/continents/filters_docstrings")
def continents_filters_doctrings():
    ret = {}
    for param, f in fields_dict.items():
        ret[param] = {
            "key": f.param,
            "entityType": "continents",
            "docstring": f.docstring,
            "documentationLink": f.documentation_link,
            "alternateNames": f.alternate_names,
        }
    return jsonify(ret)
