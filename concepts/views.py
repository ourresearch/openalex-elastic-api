from flask import Blueprint, request

from concepts.fields import fields_dict
from concepts.schemas import MessageSchema
from core.export import generate_group_by_csv, is_group_by_export
from core.filters_view import shared_filter_view
from core.schemas import FiltersWrapperSchema
from core.shared_view import shared_view
from core.utils import is_cached
from extensions import cache
from settings import CONCEPTS_INDEX

blueprint = Blueprint("concepts", __name__)


@blueprint.route("/concepts")
@cache.cached(
    timeout=24 * 60 * 60, query_string=True, unless=lambda: not is_cached(request)
)
def concepts():
    index_name = CONCEPTS_INDEX
    default_sort = ["-works_count", "id"]
    result = shared_view(request, fields_dict, index_name, default_sort)
    # export option
    if is_group_by_export(request):
        output = generate_group_by_csv(result, request)
        return output
    message_schema = MessageSchema()
    return message_schema.dump(result)


@blueprint.route("/concepts/filters/<path:params>")
def concepts_filters(params):
    index_name = CONCEPTS_INDEX
    results = shared_filter_view(request, params, fields_dict, index_name)
    filters_schema = FiltersWrapperSchema()
    return filters_schema.dump(results)
