from flask import Blueprint, request

from locations.fields import fields_dict
from locations.schemas import LocationsSchema, MessageSchema
from core.shared_view import shared_view
from core.utils import is_cached, process_only_fields
from extensions import cache

blueprint = Blueprint("locations", __name__)

LOCATIONS_INDEX = "locations-v2"


@blueprint.route("/locations")
@cache.cached(
    timeout=24 * 60 * 60, query_string=True, unless=lambda: not is_cached(request)
)
def locations():
    index_name = LOCATIONS_INDEX
    default_sort = ["work_id", "native_id"]
    only_fields = process_only_fields(request, LocationsSchema)
    result = shared_view(request, fields_dict, index_name, default_sort, connection='v2')
    message_schema = MessageSchema(only=only_fields)
    return message_schema.dump(result)
