from flask import Blueprint, jsonify, request

from core.shared_view import shared_view
from works.fields import fields_dict
from works.schemas import MessageSchema

blueprint = Blueprint("works", __name__)


@blueprint.route("/")
def index():
    return jsonify(
        {
            "version": "0.1",
            "documentation_url": "/docs",
            "msg": "Don't panic",
        }
    )


@blueprint.route("/works")
def works():
    index_name = "works-v7-*,-*invalid-data"
    default_sort = ["-publication_date"]
    result = shared_view(request, fields_dict, index_name, default_sort)
    message_schema = MessageSchema()
    return message_schema.dump(result)
