from flask import Blueprint, request

from core.filters_view import shared_filter_view
from core.schemas import FiltersWrapperSchema
from core.shared_view import shared_view
from core.utils import is_cached
from extensions import cache
from settings import VENUES_INDEX
from venues.fields import fields_dict
from venues.schemas import MessageSchema

blueprint = Blueprint("venues", __name__)


@blueprint.route("/venues")
@cache.cached(
    timeout=24 * 60 * 60, query_string=True, unless=lambda: not is_cached(request)
)
def venues():
    index_name = VENUES_INDEX
    default_sort = ["-works_count", "id"]
    result = shared_view(request, fields_dict, index_name, default_sort)
    message_schema = MessageSchema()
    return message_schema.dump(result)


@blueprint.route("/venues/filters/<path:params>")
def venues_filters(params):
    index_name = VENUES_INDEX
    results = shared_filter_view(params, fields_dict, index_name)
    filters_schema = FiltersWrapperSchema()
    return filters_schema.dump(results)
