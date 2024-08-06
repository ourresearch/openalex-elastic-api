from flask import Blueprint, request, jsonify

from config.entity_config import entity_configs_dict
from config.property_config import property_configs_dict
from oql.query import Query
from oql.schemas import QuerySchema
from oql.results_table import ResultTable
from oql.redshift import build_redshift_query, execute_redshift_query


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
    if query.use_redshift():
        print(f"Detected using in query: {query_string}")
        redshift_query = build_redshift_query(query_string)
        redshift_results = execute_redshift_query(redshift_query)
        json_data = {"results": []}
        for r in redshift_results:
            if "get subfields" in query_string:
                json_data["results"].append(
                    {
                        "id": f"https://openalex.org/subfields/{r[0]}",
                        "display_name": r[1],
                        "works_count": r[2],
                        "share": r[3],
                    }
                )
            else:
                json_data["results"].append(
                    {
                        "id": f"https://openalex.org/types/{r[0]}",
                        "display_name": r[0],
                        "works_count": r[1],
                    }
                )
        print(json_data)
        if "get subfields" in query_string:
            results_table = ResultTable(
                "subfields", ["id", "display_name", "works_count", "share"], json_data
            )
        else:
            results_table = ResultTable(
                "types", ["id", "display_name", "works_count"], json_data
            )
        results_table_response = results_table.response()
        results_table_response["meta"] = {
            "count": len(redshift_results),
            "page": query.page,
            "per_page": query.per_page,
            "q": query_string,
            "oql": query.oql_query(),
            "v1": None,
            "redshift_query": redshift_query,
        }
        # reorder the dictionary
        results_table_response = {
            "meta": results_table_response.pop("meta"),
            "results": results_table_response.pop("results"),
        }
        return jsonify(results_table_response)
    elif query.is_valid():
        json_data = query.execute()
    else:
        return jsonify({"error": "Invalid query"}), 400
    if format == "ui":
        entity = query.entity
        columns = query.columns
        results_table = ResultTable(entity, columns, json_data)
        results_table_response = results_table.response()
        results_table_response["meta"] = {
            "count": results_table.count(),
            "page": query.page,
            "per_page": query.per_page,
            "q": query_string,
            "oql": query.oql_query(),
            "v1": query.old_query(),
        }

        # reorder the dictionary
        results_table_response = {
            "meta": results_table_response.pop("meta"),
            "results": results_table_response.pop("results"),
        }
        return jsonify(results_table_response)
    else:
        return json_data


@blueprint.route("/entities/config", methods=["GET"])
def entities_config():
    config = {}
    for entity in entity_configs_dict:
        config[entity] = entity_configs_dict[entity]
        config[entity]["properties"] = property_configs_dict[entity]
    return jsonify(config)


@blueprint.route("/entities/<entity>/config", methods=["GET"])
def entity_config(entity):
    if entity not in entity_configs_dict:
        return jsonify({"error": "Entity not found"}), 404

    config = entity_configs_dict[entity]
    config["properties"] = property_configs_dict[entity]
    return jsonify(config)
