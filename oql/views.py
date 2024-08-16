from flask import Blueprint, request, jsonify

from combined_config import all_entities_config
from oql.query import Query
from oql.schemas import QuerySchema
from oql.results_table import ResultTable
from oql.search import Search, is_cache_expired, get_existing_search
from oql.searchv2 import SearchV2, get_existing_search_v2, \
    QueryParameters, update_existing_search_v2
from oql.util import from_dict

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


@blueprint.route("/searches-v2", methods=["POST"])
def store_search():
    query_params = from_dict(QueryParameters, request.json)
    if not query_params.is_valid():
        return jsonify({'error': 'Search invalid'}), 400
    existing_search = get_existing_search_v2(query_params.id_hash())
    if existing_search and not existing_search.is_cache_expired():
        return jsonify(existing_search), 200

    s = SearchV2(query_params=query_params)
    s.save(enqueue=True)

    return jsonify(s.to_dict()), 201


@blueprint.route("/searches-v2/<id>", methods=["GET"])
def get_search(id):
    search = get_existing_search_v2(id)
    if not search:
        return jsonify({"error": "Search not found"}), 404

    return jsonify(search)


@blueprint.route("/searches-v2/<id>/update", methods=["PUT"])
def update_search(id):
    query_params = from_dict(QueryParameters, request.json)
    if not query_params.is_valid():
        return jsonify({'error': 'Search invalid'}), 400
    search = update_existing_search_v2(id, query_params)
    if not search:
        return jsonify({"error": "Search not found"}), 404
    return jsonify(search.to_dict()), 204


@blueprint.route("/searches-v2/<id>/return_columns/<column>", methods=["PATCH"])
def add_search_query_column(id, column):
    search = get_existing_search_v2(id)
    if not search:
        return jsonify({"error": "Search not found"}), 404
    if not search.query_params.add_return_column(column):
        return jsonify({"error": f"Invalid column: {column}"}), 400
    search.save()
    return jsonify(search.to_dict()), 204


@blueprint.route("/searches-v2/<id>/return_columns/<column>",
                 methods=["DELETE"])
def delete_search_query_column(id, column):
    search = get_existing_search_v2(id)
    if not search:
        return jsonify({"error": "Search not found"}), 404
    if not search.query_params.remove_return_column(column):
        return jsonify({"error": f"Column not present: \"{column}\""}), 400
    search.save()
    return jsonify(search.to_dict()), 204


# TODO
# @blueprint.route("/searches-v2/<id>/get_works_where/<clause>", methods=["PATCH"])
# def update_search_query_get_works_where(id, clause):
#     search = get_existing_search(id)
#     if not search:
#         return jsonify({"error": "Search not found"}), 404
#     if not gww.is_valid():
#         return jsonify({"error": "Invalid clause"}), 400
#     search.query_params.get_works_where = gww
#     search.save()
#     return jsonify(search.to_dict()), 204


@blueprint.route("/entities/config", methods=["GET"])
def entities_config():
    return jsonify(all_entities_config)


@blueprint.route("/entities/<entity>/config", methods=["GET"])
def entity_config(entity):
    if entity not in all_entities_config:
        return jsonify({"error": "Entity not found"}), 404

    config = all_entities_config[entity]
    return jsonify(config)
