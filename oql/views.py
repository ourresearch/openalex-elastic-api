from flask import Blueprint, request, jsonify

from combined_config import all_entities_config
from oql.query import Query, QueryNew
from oql.schemas import QuerySchema
from oql.results_table import ResultTable
from oql.search import Search, get_existing_search

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
    # params
    entity = request.args.get("summarize_by")
    filters = request.args.get("filters")
    columns = request.args.get("return_columns")
    sort_by_column = request.args.get("sort_by_column")
    sort_by_order = request.args.get("sort_by_order")

    # parse lists
    if columns:
        columns = columns.split(",")
        columns = [column.strip() for column in columns]

    # query object
    query = QueryNew(
        entity=entity,
        columns=columns,
        filters=filters,
        sort_by_column=sort_by_column,
        sort_by_order=sort_by_order,
    )

    json_data = query.execute()

    # results table
    results_table = ResultTable(
        entity=entity,
        columns=columns,
        json_data=json_data,
        page=1,
        per_page=100,
    )
    results_table_response = results_table.response()
    return jsonify(results_table_response)


@blueprint.route("/searches", methods=["POST"])
def store_search():
    query = request.json.get("query")
    if not query:
        return jsonify({"error": "No query provided"}), 400

    s = Search(query=query)
    s.save()
    return jsonify(s.to_dict()), 201


@blueprint.route("/searches/<id>", methods=["GET"])
def get_search(id):
    search = get_existing_search(id)
    if not search:
        return jsonify({"error": "Search not found"}), 404

    return jsonify(search)


@blueprint.route("/entities/config", methods=["GET"])
def entities_config():
    return jsonify(all_entities_config)


@blueprint.route("/entities/<entity>/config", methods=["GET"])
def entity_config(entity):
    if entity not in all_entities_config:
        return jsonify({"error": "Entity not found"}), 404

    config = all_entities_config[entity]
    return jsonify(config)
