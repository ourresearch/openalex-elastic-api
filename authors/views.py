from flask import Blueprint, current_app, jsonify, request

from authors.fields import fields_dict
from authors.schemas import MessageSchema
from core.exceptions import APIError
from core.shared_view import shared_view

blueprint = Blueprint("authors", __name__)


@blueprint.route("/authors")
def authors():
    index_name = "authors-v1"
    default_sort = "-works_count"
    result = shared_view(request, fields_dict, index_name, default_sort)
    message_schema = MessageSchema()
    return message_schema.dump(result)


@blueprint.errorhandler(APIError)
def handle_exception(err):
    """Return custom JSON when APIError or its children are raised"""
    response = {"error": err.description, "message": ""}
    if len(err.args) > 0:
        response["message"] = err.args[0]
    # Add some logging so that we can monitor different types of errors
    current_app.logger.error("{}: {}".format(err.description, response["message"]))
    return jsonify(response), err.code
