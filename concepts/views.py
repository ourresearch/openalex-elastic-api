from flask import Blueprint, request

from concepts.fields import fields_dict
from concepts.schemas import MessageSchema
from core.shared_view import shared_view

blueprint = Blueprint("concepts", __name__)


@blueprint.route("/concepts")
def venues():
    index_name = "concepts-v1"
    default_sort = "-works_count"
    result = shared_view(request, fields_dict, index_name, default_sort)
    message_schema = MessageSchema()
    return message_schema.dump(result)
