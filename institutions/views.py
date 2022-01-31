from flask import Blueprint, request

from core.shared_view import shared_view
from institutions.fields import fields_dict
from institutions.schemas import MessageSchema

blueprint = Blueprint("institutions", __name__)


@blueprint.route("/institutions")
def institutions():
    index_name = "institutions-v2"
    default_sort = ["-works_count", "id"]
    result = shared_view(request, fields_dict, index_name, default_sort)
    message_schema = MessageSchema()
    return message_schema.dump(result)
