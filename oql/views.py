from flask import Blueprint, request, jsonify

from oql.query import Query
from oql.schemas import QuerySchema
from oql.results_table import ResultTable


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
    format = request.args.get("format")
    query = Query(query_string)
    if query.is_valid():
        json_data = query.execute()
    else:
        return jsonify({"error": "Invalid query"}), 400
    if format == "ui":
        entity = query.entity
        columns = query.columns
        results_table = ResultTable(entity, columns, json_data)
        results_table_response = results_table.response()
        results_table_response['meta'] = {
            "q": query_string,
            "oql": query.oql_query(),
            "v1": query.old_query(),
        }

        # reorder the dictionary
        results_table_response = {
            "meta": results_table_response.pop("meta"),
            "header": results_table_response.pop("header"),
            "body": results_table_response.pop("body"),
        }
        return jsonify(results_table_response)
    else:
        return json_data
