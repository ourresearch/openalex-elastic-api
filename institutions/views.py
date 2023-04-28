from flask import Blueprint, request, jsonify

from core.export import export_group_by, is_group_by_export
from core.filters_view import shared_filter_view
from core.histogram import shared_histogram_view
from core.schemas import FiltersWrapperSchema, HistogramWrapperSchema
from core.shared_view import shared_view
from core.utils import is_cached, process_only_fields, get_valid_fields
from extensions import cache
from institutions.fields import fields_dict
from institutions.schemas import InstitutionsSchema, MessageSchema
from settings import INSTITUTIONS_INDEX

blueprint = Blueprint("institutions", __name__)


@blueprint.route("/institutions")
@cache.cached(
    timeout=24 * 60 * 60, query_string=True, unless=lambda: not is_cached(request)
)
def institutions():
    index_name = INSTITUTIONS_INDEX
    default_sort = ["-works_count", "id"]
    only_fields = process_only_fields(request, InstitutionsSchema)
    result = shared_view(request, fields_dict, index_name, default_sort)
    # export option
    if is_group_by_export(request):
        return export_group_by(result, request)
    message_schema = MessageSchema(only=only_fields)
    return message_schema.dump(result)


@blueprint.route("/institutions/filters/<path:params>")
def institutions_filters(params):
    index_name = INSTITUTIONS_INDEX
    results = shared_filter_view(request, params, fields_dict, index_name)
    filters_schema = FiltersWrapperSchema()
    return filters_schema.dump(results)


@blueprint.route("/institutions/histogram/<string:param>")
def institutions_histograms(param):
    index_name = INSTITUTIONS_INDEX
    result = shared_histogram_view(request, param, fields_dict, index_name)
    histogram_schema = HistogramWrapperSchema()
    return histogram_schema.dump(result)


@blueprint.route("/institutions/valid_fields")
def institutions_valid_fields():
    valid_fields = get_valid_fields(fields_dict)
    return jsonify(valid_fields)
