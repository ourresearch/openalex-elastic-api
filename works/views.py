from elasticsearch_dsl import Search
from flask import Blueprint, current_app, jsonify, request

from core.exceptions import APIError
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
    index_name = "works-v4-*,-*invalid-data"
    default_sort = "-publication_date"
    result = shared_view(request, fields_dict, index_name, default_sort)
    message_schema = MessageSchema()
    return message_schema.dump(result)


@blueprint.route("/complete")
def complete():
    q = request.args.get("q")
    s = Search(index="works-v2-*,-*invalid-data")
    s = s.suggest("title_suggestion", q, completion={"field": "display_name.complete"})
    response = s.execute()
    title_results = [r.text for r in response.suggest.title_suggestion[0].options]
    return jsonify(title_results)


@blueprint.errorhandler(APIError)
def handle_exception(err):
    """Return custom JSON when APIError or its children are raised"""
    response = {"error": err.description, "message": ""}
    if len(err.args) > 0:
        response["message"] = err.args[0]
    # Add some logging so that we can monitor different types of errors
    current_app.logger.error("{}: {}".format(err.description, response["message"]))
    return jsonify(response), err.code
