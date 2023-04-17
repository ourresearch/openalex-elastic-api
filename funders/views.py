from flask import Blueprint, request

from core.export import export_group_by, is_group_by_export
from core.filters_view import shared_filter_view
from core.histogram import shared_histogram_view
from core.schemas import FiltersWrapperSchema, HistogramWrapperSchema
from core.shared_view import shared_view
from core.utils import is_cached, process_only_fields
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
