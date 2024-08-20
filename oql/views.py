from flask import Blueprint, request, jsonify

from combined_config import all_entities_config
from oql.query import Query, QueryNew
from oql.schemas import QuerySchema
from oql.results_table import ResultTable
from oql.search import Search, get_existing_search
from oql.search_v2 import SearchV2, get_existing_search_v2, \
    QueryParameters, update_existing_search_v2

from oql.util import from_dict, parse_bool, random_md5

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
    columns = request.args.get("return")
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
        filter_by=[],
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


@blueprint.route("/searches-v2", methods=["POST"])
def store_search_v2():
    query_params = from_dict(QueryParameters, request.json)
    if not query_params.is_valid():
        return jsonify({'error': 'Search invalid'}), 400
    # existing_search = get_existing_search_v2(query_params.id_hash())
    # if existing_search and not existing_search.is_cache_expired():
    #     return jsonify(existing_search), 200

    s = SearchV2(query_params=query_params)
    s.id = random_md5()
    s.save(enqueue=True)

    return jsonify(s.to_dict()), 201


@blueprint.route("/searches-v2/<id>", methods=["GET"])
def get_search_v2(id):
    search = get_existing_search_v2(id)
    if not search:
        return jsonify({"error": "Search not found"}), 404

    return jsonify(search.to_dict()), 200


@blueprint.route("/searches-v2/<id>/update", methods=["PUT"])
def update_search(id):
    query_params = from_dict(QueryParameters, request.json)
    if not query_params.is_valid():
        return jsonify({'error': 'Search invalid'}), 400
    search = update_existing_search_v2(id, query_params)
    if not search:
        return jsonify({"error": "Search not found"}), 404
    return jsonify(search.to_dict()), 200


@blueprint.route("/searches-v2/<id>/return_columns/<column>", methods=["PATCH"])
def add_search_query_column(id, column):
    search = get_existing_search_v2(id)
    if not search:
        return jsonify({"error": "Search not found"}), 404
    if not search.query_params.add_return_column(column):
        return jsonify({"error": f"Invalid column: {column}"}), 400
    search.save()
    return jsonify(search.to_dict()), 200


@blueprint.route("/searches-v2/<id>/return_columns/<column>",
                 methods=["DELETE"])
def delete_search_query_column(id, column):
    search = get_existing_search_v2(id)
    if not search:
        return jsonify({"error": "Search not found"}), 404
    if not search.query_params.remove_return_column(column):
        return jsonify({"error": f"Column not present: \"{column}\""}), 400
    search.save()
    return jsonify(search.to_dict()), 200


@blueprint.route("/searches-v2/<id>/sort_by/column/<column>",
                 methods=["PATCH"])
def set_search_query_sort_by_column(id, column):
    search = get_existing_search_v2(id)
    if not search:
        return jsonify({"error": "Search not found"}), 404
    search.query_params.sort_by.column = column
    if not search.query_params.sort_by.is_valid(search.query_params.return_columns):
        return jsonify(
            {"error": f"Sort by column not currently in return columns: \"{column}\""}), 400
    search.save()
    return jsonify(search.to_dict()), 200


@blueprint.route("/searches-v2/<id>/sort_by/dir/<dir>",
                 methods=["PATCH"])
def set_search_query_sort_by_dir(id, dir):
    search = get_existing_search_v2(id)
    if not search:
        return jsonify({"error": "Search not found"}), 404
    search.query_params.sort_by.direction = dir
    if not search.query_params.sort_by.is_valid(search.query_params.return_columns):
        return jsonify(
            {"error": f"Sort by direction not valid: \"{dir}\""}), 400
    search.save()
    return jsonify(search.to_dict()), 200


@blueprint.route("/searches-v2/<id>/summarize/<bool_str>",
                 methods=["PATCH"])
def set_search_query_summarize(id, bool_str):
    search = get_existing_search_v2(id)
    if not search:
        return jsonify({"error": "Search not found"}), 404
    try:
        summarize = parse_bool(bool_str)
    except ValueError:
        return jsonify({"error": f"Invalid boolean string: \"{bool_str}\""}), 400
    search.query_params.summarize = summarize
    search.save()
    return jsonify(search.to_dict()), 200


@blueprint.route("/searches-v2/<id>/get_works_where", methods=["PATCH"])
def update_search_query_get_works_where(id):
    search = get_existing_search_v2(id)
    if not search:
        return jsonify({"error": "Search not found"}), 404
    search.query_params.get_works_where = request.json
    # new_clause = from_dict(Clause, request.json)
    # if not new_clause.is_valid():
    #     return jsonify({"error": f"Invalid clause"}), 400
    # updated = search.query_params.get_works_where.update_clause(clause_id, new_clause)
    # if not updated:
    #     return jsonify({"error": "Unable to update clause"}), 400
    search.save()
    return jsonify(search.to_dict()), 200


@blueprint.route("/searches-v2/<id>/summarize_by_where", methods=["PATCH"])
def update_search_query_summarize_by_where(id):
    search = get_existing_search_v2(id)
    if not search:
        return jsonify({"error": "Search not found"}), 404
    search.query_params.summarize_by_where = request.json
    # new_clause = from_dict(Clause, request.json)
    # if not new_clause.is_valid():
    #     return jsonify({"error": f"Invalid clause"}), 400
    # updated = search.query_params.summarize_by_where.update_clause(clause_id, new_clause)
    # if not updated:
    #     return jsonify({"error": "Unable to update clause"}), 400
    search.save()
    return jsonify(search.to_dict()), 200


@blueprint.route("/entities/config", methods=["GET"])
def entities_config():
    return jsonify(all_entities_config)


@blueprint.route("/entities/<entity>/config", methods=["GET"])
def entity_config(entity):
    if entity not in all_entities_config:
        return jsonify({"error": "Entity not found"}), 404

    config = all_entities_config[entity]
    return jsonify(config)
