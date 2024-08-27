from flask import Blueprint, request, jsonify
from oqo_validate.validate import OQOValidator

from combined_config import all_entities_config
from oql.query import QueryNew
from oql.results_table import ResultTable
from oql.search import Search, get_existing_search

blueprint = Blueprint("oql", __name__)


@blueprint.route("/results", methods=["GET", "POST"])
def results():
    # set results from json
    entity = request.json.get("summarize_by") or "works"
    filters = request.json.get("filters") or []
    columns = request.json.get("return_columns")
    sort_by_column = request.json.get("sort_by", {}).get("column_id", "display_name")
    sort_by_order = request.json.get("sort_by", {}).get("direction", "asc")

    # validate the query
    oqo = OQOValidator(all_entities_config)
    ok, error = oqo.validate({
        "summarize_by": entity,
        "filters": filters,
        "return_columns": columns,
        "sort_by_column": sort_by_column,
        "sort_by_order": sort_by_order,
    })

    if not ok:
        return jsonify({"invalid query error": error}), 400

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
