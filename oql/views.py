import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
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


@blueprint.route("/results", methods=["GET", "POST"])
def results():
    # params
    if request.method == "GET":
        entity = request.args.get("summarize_by") or "works"
        filters = request.args.get("filters")
        columns = request.args.get("return_columns")
        sort_by_column = request.args.get("sort_by_column")
        sort_by_order = request.args.get("sort_by_order")
    else:
        entity = request.json.get("summarize_by") or "works"
        filters = request.json.get("filters")
        columns = request.json.get("return_columns")
        sort_by_column = request.json.get("sort_by_column")
        sort_by_order = request.json.get("sort_by_order")

    # parse lists
    if request.method == "GET" and columns:
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


# bulk natLang test endpoint
# accepts list of {"test_id": "kj33F", "prompt": "show me works from 2021 from Harvard"}
@blueprint.route("/bulk_test", methods=["POST"])
def bulk_test():
    def process_nat_lang_test(test):
        params = {'natural_language': test['prompt'],
                  'mailto': 'team@ourresearch.org'}
        r = requests.get('https://api.openalex.org/text/oql', params=params)
        test['oqo'] = r.json()
        return test

    def process_query_test(test):
        def create_search(query):
            params = {
                'query': query,
                'mailto': 'team@ourresearch.org'
            }
            r = requests.post("https://api.openalex.org/searches",
                              params=params)
            r.raise_for_status()
            return r.json()['id']

        def get_search_state(search_id):
            url = f"https://api.openalex.org/searches/{search_id}"
            params = {'mailto': 'team@ourresearch.org'}
            r = requests.get(url, params=params)
            r.raise_for_status()
            return r.json()

        def poll_search_until_ready(search_id, timeout):
            start_time = time.time()
            while True:
                result = get_search_state(search_id)
                if result['is_ready']:
                    return result, time.time() - start_time

                if time.time() - start_time >= timeout:
                    raise TimeoutError("Search timed out")

                time.sleep(1)

        try:
            search_id = create_search(test['query'])
            timeout = test.get('searchTimeout',
                               30)
            result, elapsed_time = poll_search_until_ready(search_id, timeout)

            test['search_result'] = {
                'id': search_id,
                'is_ready': True,
                'results': result['results'],
                'elapsed_time': elapsed_time
            }
        except Exception as e:
            test['search_result'] = {
                'error': str(e)
            }

        return test

    test_data = request.json

    responses = []
    with ThreadPoolExecutor(max_workers=20) as executor:
        futures = {}
        for test in test_data:
            if 'prompt' in test:
                futures[executor.submit(process_nat_lang_test, test)] = test
            elif 'query' in test:
                futures[executor.submit(process_query_test, test)] = test
            else:
                test['error'] = "Invalid input: missing 'prompt' or 'query'"
                responses.append(test)

        for future in as_completed(futures):
            try:
                result = future.result()
                responses.append(result)
            except Exception as exc:
                test = futures[future]
                test['error'] = str(exc)
                responses.append(test)

    return jsonify(responses)

