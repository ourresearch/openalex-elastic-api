import json
import os
import uuid

import redis
from flask import Blueprint, request, jsonify, make_response
from redis.client import Redis

from combined_config import all_entities_config
from oql.process_bulk_tests import decode_redis_data
from oql.query import QueryNew
from oql.results_table import ResultTable
from oql.search import Search, get_existing_search
from oql.validate import OQOValidator

blueprint = Blueprint("oql", __name__)
redis_client = Redis.from_url(os.environ.get("REDIS_DO_URL"))


def add_cors_headers(response):
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Methods'] = 'POST, GET, OPTIONS'
    response.headers['Access-Control-Allow-Headers'] = '*'
    return response


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

    # if not ok:
    # return jsonify({"invalid query error": error}), 400

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
        total_count=query.total_count,
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


@blueprint.route('/test_stories', methods=['OPTIONS'])
def bulk_test_cors():
    return add_cors_headers(make_response()), 200


@blueprint.route('/test_stories', methods=['POST'])
def create_testing_job():
    try:
        # If the content type is application/json, Flask should have already parsed it
        if request.is_json:
            tests = request.json
        else:
            # If not, we'll try to parse it ourselves
            tests = json.loads(request.data)

        if not tests:
            return add_cors_headers(
                jsonify({'error': 'No tests provided'})), 400

        job_id = str(uuid.uuid4())

        # Create a new job in Redis
        job_data = {
            'status': 'queued',
            'tests': json.dumps(tests),
            'results': json.dumps([]),
            'is_completed': 'false'
        }

        # Use pipeline for atomic operation
        pipe = redis_client.pipeline()
        pipe.hset(f'job:{job_id}', mapping=job_data)
        pipe.lpush('job_queue', job_id)
        pipe.execute()

        # Verify the job was created
        stored_job = redis_client.hgetall(f'job:{job_id}')
        if not stored_job:
            return jsonify({'error': 'Failed to create job'}), 500

        return jsonify({'job_id': job_id, 'message': 'Job queued'}), 202

    except json.JSONDecodeError:
        return jsonify({'error': 'Invalid JSON in request body'}), 400
    except redis.RedisError as e:
        return jsonify({'error': f'Redis error: {str(e)}'}), 500
    except Exception as e:
        return jsonify({'error': f'Unexpected error: {str(e)}'}), 500


@blueprint.route('/test_stories/<job_id>', methods=['OPTIONS'])
def job_status_cors(job_id):
    return add_cors_headers(make_response()), 200


@blueprint.route('/test_stories/<job_id>', methods=['GET'])
def job_status(job_id):
    job = redis_client.hgetall(f'job:{job_id}')
    if not job:
        return jsonify({'status': 'error', 'message': 'Invalid job ID'}), 404
    job = decode_redis_data(job)

    return jsonify({
        'status': job['status'],
        'is_completed': job['is_completed'],
        'results': job['results']})


@blueprint.after_request
def add_cors_headers_to_test_stories(response):
    if request.path.startswith('/test_stories'):
        return add_cors_headers(response)
    return response
