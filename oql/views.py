from flask import Blueprint, request, jsonify

from combined_config import all_entities_config
from oql.query import Query
from oql.schemas import QuerySchema
from oql.results_table import ResultTable
from oql.search import Search, get_existing_search, is_cache_expired


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
@blueprint.route("/entities", methods=["GET"])
def results():
    query_string = request.args.get("q")
    page = request.args.get("page")
    per_page = request.args.get("per-page")
    format = request.args.get("format")
    if not query_string:
        return {
            "meta": {
                "count": 0,
                "page": 1,
                "per_page": 10,
                "q": "",
                "oql": "",
                "v1": "",
            },
            "results": [],
        }
    query = Query(query_string, page, per_page)
    if format == "ui":
        entity = query.entity
        columns = query.columns or all_entities_config[entity]["showOnTablePage"]
        json_data = query.execute()
        print(json_data)
        results_table = ResultTable(
            entity, columns, json_data
        )
        results_table_response = results_table.response()
        results_table_response["meta"] = {
            "count": results_table.count(),
            "page": query.page,
            "per_page": query.per_page,
            "q": query_string,
            "oql": query.oql_query(),
            "v1": None,
        }
        # reorder the dictionary
        results_table_response = {
            "meta": results_table_response.pop("meta"),
            "results": results_table_response.pop("results"),
        }
        return jsonify(results_table_response)


@blueprint.route("/searches", methods=["POST"])
def store_search():
    q = request.json.get("q")
    if not q:
        return jsonify({"error": "No query provided"}), 400

    s = Search(q=q)
    existing_search = get_existing_search(s.id)
    if existing_search and not is_cache_expired(existing_search):
        return jsonify(existing_search), 200

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
