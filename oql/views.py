import json
import time
import uuid
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from queue import Queue
from threading import Thread

import requests
from flask import Blueprint, request, jsonify, Response, make_response

from combined_config import all_entities_config
from oql.query import QueryNew
from oql.results_table import ResultTable
from oql.search import Search, get_existing_search
from oql.validate import OQOValidator

blueprint = Blueprint("oql", __name__)


@blueprint.route("/results", methods=["GET", "POST"])
def results():
    # set results from json
    entity = request.json.get("summarize_by") or "works"
    filters = request.json.get("filters") or []
    columns = request.json.get("return_columns")
    sort_by_column = request.json.get("sort_by", {}).get("column_id",
                                                         "display_name")
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


# Dictionary to store queue-specific results
queue_results = {}

# Create a ThreadPoolExecutor with 30 threads
executor = ThreadPoolExecutor(max_workers=10)


def process_query_test(test):
    def create_search(query):
        params = {
            'query': query,
            'mailto': 'team@ourresearch.org'
        }
        r = requests.post("https://api.openalex.org/searches", params=params)
        r.raise_for_status()
        return r.json()['id']

    def get_search_state(search_id):
        url = f"https://api.openalex.org/searches/{search_id}"
        params = {'mailto': 'team@ourresearch.org'}
        r = requests.get(url, params=params)
        r.raise_for_status()
        return r.json()

    try:
        search_id = create_search(test['query'])
        timeout = test.get('searchTimeout', 30)
        start_time = time.time()
        while True:
            result = get_search_state(search_id)
            if result['is_ready']:
                elapsed_time = time.time() - start_time
                return {
                    'id': test['test_id'],
                    'case': 'queryToSearch',
                    'isPassing': len(result['results']) > 0,
                    'details': {
                        'searchId': search_id,
                        'elapsedTime': elapsed_time,
                        'resultsCount': len(result['results']),
                    }
                }
            if time.time() - start_time >= timeout:
                return {
                    'id': test['test_id'],
                    'case': 'queryToSearch',
                    'isPassing': False,
                    'details': {
                        'error': 'Search timed out',
                        'test': test
                    }
                }
            time.sleep(1)
    except Exception as e:
        return {
            'id': test['test_id'],
            'case': 'queryToSearch',
            'isPassing': False,
            'details': {
                'error': str(e),
                'test': test
            }
        }


def process_nat_lang_test(test):
    params = {
        'natural_language': test['prompt'],
        'mailto': 'team@ourresearch.org'
    }
    try:
        r = requests.get('https://api.openalex.org/text/oql', params=params)
        r.raise_for_status()
        oqo = r.json()
        return {
            'id': test['test_id'],
            'case': 'natLang',
            'prompt': test['prompt'],
            'oqo': oqo
        }
    except Exception as e:
        return {
            'id': test['test_id'],
            'case': 'natLang',
            'prompt': test['prompt'],
            'error': str(e)
        }


def process_test(test):
    if 'query' in test:
        return process_query_test(test)
    elif 'prompt' in test:
        return process_nat_lang_test(test)
    else:
        return {'error': 'Invalid test format', 'test': test}


def process_tests(tests, queue_id):
    futures = []
    for test in tests:
        futures.append(executor.submit(process_test, test))

    nat_lang_results = defaultdict(list)

    for future in as_completed(futures):
        result = future.result()
        if result['case'] == 'natLang':
            nat_lang_results[result['id']].append(result)
        else:
            queue_results[queue_id].put(result)

    # Send grouped natLang results
    for test_id, results in nat_lang_results.items():
        grouped_result = {
            'id': test_id,
            'case': 'natLang',
            'results': results
        }
        queue_results[queue_id].put(grouped_result)

    # Signal that all tests are completed
    queue_results[queue_id].put({'status': 'all_completed'})


@blueprint.route('/bulk_test', methods=['POST'])
def bulk_test():
    tests = json.loads(request.data)
    queue_id = str(uuid.uuid4())
    queue_results[queue_id] = Queue()

    executor.submit(process_tests, tests, queue_id)
    resp = make_response(
        jsonify({'queue_id': queue_id, 'message': 'Tests started'}), 202)
    resp.headers['Access-Control-Allow-Origin'] = '*'
    return resp


@blueprint.route('/stream/<queue_id>')
def stream(queue_id):
    def event_stream():
        while True:
            if queue_id in queue_results:
                if not queue_results[queue_id].empty():
                    result = queue_results[queue_id].get()
                    yield f"data: {json.dumps(result)}\n\n"
                    if result.get('status') == 'all_completed':
                        break
                else:
                    yield f"data: {json.dumps({'status': 'processing'})}\n\n"
            else:
                yield f"data: {json.dumps({'status': 'error', 'message': 'Invalid queue ID'})}\n\n"
                break
            time.sleep(0.5)

        # Clean up the queue when done
        if queue_id in queue_results:
            del queue_results[queue_id]

    resp = make_response(
        Response(event_stream(), content_type='text/event-stream'))
    resp.headers['Access-Control-Allow-Origin'] = '*'
    return resp
