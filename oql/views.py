from flask import Blueprint, request, jsonify

from oql.query import Query
from oql.schemas import QuerySchema


blueprint = Blueprint("oql", __name__)


@blueprint.route("/query", methods=["GET", "POST"])
def query():
    if request.method == "GET":
        query_string = request.args.get("q")
    else:
        query_string = request.json.get("q")

    query_result = Query(query_string).to_dict()
    query_schema = QuerySchema()
    return query_schema.dump(query_result)


@blueprint.route("/results", methods=["GET"])
def results():
    query_string = request.args.get("q")
    query = Query(query_string)
    if query.is_valid():
        return jsonify(query.execute())
    else:
        return jsonify({"error": "Invalid query"}), 400

