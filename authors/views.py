from flask import Blueprint, request

from authors.fields import fields_dict
from authors.schemas import MessageSchema
from core.shared_view import shared_view

blueprint = Blueprint("authors", __name__)


@blueprint.route("/authors")
def authors():
    index_name = "authors-v6"
    default_sort = ["-works_count"]
    result = shared_view(request, fields_dict, index_name, default_sort)
    message_schema = MessageSchema()
    return message_schema.dump(result)
