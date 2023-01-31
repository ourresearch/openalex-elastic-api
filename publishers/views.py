from flask import Blueprint, request

from core.export import export_group_by, is_group_by_export
from core.filters_view import shared_filter_view
from core.histogram import shared_histogram_view
from core.schemas import FiltersWrapperSchema, HistogramWrapperSchema
from core.shared_view import shared_view
from core.utils import is_cached
from extensions import cache
from publishers.fields import fields_dict
from publishers.schemas import MessageSchema
from settings import PUBLISHERS_INDEX

blueprint = Blueprint("publishers", __name__)


@blueprint.route("/publishers")
@cache.cached(
    timeout=24 * 60 * 60, query_string=True, unless=lambda: not is_cached(request)
)
def publishers():
    index_name = PUBLISHERS_INDEX
    default_sort = ["-works_count", "id"]
    result = shared_view(request, fields_dict, index_name, default_sort)
    # export option
    if is_group_by_export(request):
        return export_group_by(result, request)
    message_schema = MessageSchema()
    return message_schema.dump(result)


@blueprint.route("/publishers/filters/<path:params>")
def publishers_filters(params):
    index_name = PUBLISHERS_INDEX
    results = shared_filter_view(request, params, fields_dict, index_name)
    filters_schema = FiltersWrapperSchema()
    return filters_schema.dump(results)


@blueprint.route("/publishers/histogram/<string:param>")
def publishers_histograms(param):
    index_name = PUBLISHERS_INDEX
    result = shared_histogram_view(request, param, fields_dict, index_name)
    histogram_schema = HistogramWrapperSchema()
    return histogram_schema.dump(result)
