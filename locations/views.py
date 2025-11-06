from flask import Blueprint, request

from locations.fields import fields_dict
from locations.schemas import LocationsSchema, MessageSchema
from core.shared_view import shared_view
from core.utils import process_only_fields

blueprint = Blueprint("locations", __name__)

LOCATIONS_INDEX = "locations-v1"


@blueprint.route("/locations")
@blueprint.route("/v2/locations")
def locations():
    index_name = LOCATIONS_INDEX
    default_sort = ["work_id", "native_id"]
    only_fields = process_only_fields(request, LocationsSchema)
    result = shared_view(request, fields_dict, index_name, default_sort, connection='walden')
    message_schema = MessageSchema(only=only_fields)
    return message_schema.dump(result)
