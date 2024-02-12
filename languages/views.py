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
from languages.fields import fields_dict
from languages.schemas import LanguagesSchema, MessageSchema
from settings import LANGUAGES_INDEX

blueprint = Blueprint("languages", __name__)


@blueprint.route("/languages")
@cache.cached(
    timeout=24 * 60 * 60, query_string=True, unless=lambda: not is_cached(request)
)
def languages():
    index_name = LANGUAGES_INDEX
    default_sort = ["-works_count", "id"]
    only_fields = process_only_fields(request, LanguagesSchema)
    result = shared_view(request, fields_dict, index_name, default_sort)
    # export option
    if is_group_by_export(request):
        return export_group_by(result, request)
    message_schema = MessageSchema(only=only_fields)
    return message_schema.dump(result)


@blueprint.route("/languages/filters/<path:params>")
def languages_filters(params):
    index_name = LANGUAGES_INDEX
    results = shared_filter_view(request, params, fields_dict, index_name)
    filters_schema = FiltersWrapperSchema()
    return filters_schema.dump(results)


@blueprint.route("/languages/histogram/<string:param>")
def languages_histograms(param):
    index_name = LANGUAGES_INDEX
    result = shared_histogram_view(request, param, fields_dict, index_name)
    histogram_schema = HistogramWrapperSchema()
    return histogram_schema.dump(result)


@blueprint.route("/languages/valid_fields")
def languages_valid_fields():
    valid_fields = get_valid_fields(fields_dict)
    return jsonify(valid_fields)


@blueprint.route("/languages/flattened_schema")
def languages_flattened_schema():
    flattened_schema = get_flattened_fields(LanguagesSchema())
    return jsonify(flattened_schema)


@blueprint.route("/languages/filters_docstrings")
def languages_filters_doctrings():
    ret = {}
    for param, f in fields_dict.items():
        ret[param] = {
            "key": f.param,
            "entityType": "languages",
            "docstring": f.docstring,
            "documentationLink": f.documentation_link,
            "alternateNames": f.alternate_names,
        }
    return jsonify(ret)
