from flask import Blueprint, request

from core.export import generate_group_by_csv, is_group_by_export
from core.filters_view import shared_filter_view
from core.histogram import shared_histogram_view
from core.schemas import FiltersWrapperSchema, HistogramWrapperSchema
from core.shared_view import shared_view
from core.utils import is_cached
from extensions import cache
from institutions.fields import fields_dict
from institutions.schemas import MessageSchema
from settings import INSTITUTIONS_INDEX

blueprint = Blueprint("institutions", __name__)


@blueprint.route("/institutions")
@cache.cached(
    timeout=24 * 60 * 60, query_string=True, unless=lambda: not is_cached(request)
)
def institutions():
    index_name = INSTITUTIONS_INDEX
    default_sort = ["-works_count", "id"]
    result = shared_view(request, fields_dict, index_name, default_sort)
    # export option
    if is_group_by_export(request):
        output = generate_group_by_csv(result)
        return output
    message_schema = MessageSchema()
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
