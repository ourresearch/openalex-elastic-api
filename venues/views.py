from flask import Blueprint, request

from core.shared_view import shared_view
from venues.fields import fields_dict
from venues.schemas import MessageSchema

blueprint = Blueprint("venues", __name__)


@blueprint.route("/venues")
def venues():
    index_name = "venues-v2"
    default_sort = ["-works_count", "id"]
    result = shared_view(request, fields_dict, index_name, default_sort)
    message_schema = MessageSchema()
    return message_schema.dump(result)
