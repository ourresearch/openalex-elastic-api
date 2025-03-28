import json
import os
import uuid

import redis
import yaml
from flask import Blueprint, request, jsonify, make_response
from redis.client import Redis

import settings
from combined_config import all_entities_config
from oql.process_bulk_tests import decode_redis_data
from oql.query import Query
from oql.results_table import ResultTable
from oql.search import Search, get_existing_search, redis_db, search_queue
from oql.validate import OQOValidator


blueprint = Blueprint("oql", __name__)
redis_db = redis.Redis.from_url(settings.CACHE_REDIS_URL)
redis_client = Redis.from_url(os.environ.get("REDIS_DO_URL"))
search_queue = settings.SEARCH_QUEUE


@blueprint.route("/searches", methods=["POST"])
def create_search():
    raw_query = request.json.get("query")
    bypass_cache = request.json.get("bypass_cache", False)

    #print("create_search")
    #print(raw_query, flush=True)

    query = Query(raw_query)

    # validate the query
    oqo = OQOValidator(all_entities_config)
    ok, error = oqo.validate(query.to_dict())
    if not ok:
        print(f"Invalid Query: {error}", flush=True)
        return jsonify({"error": "Invalid Query", "details": error, "query": raw_query}), 400

    # print("query.to_dict()")
    # print(query.to_dict(), flush=True)
    s = Search(query=query.to_dict(), redshift_sql=query.get_sql(), bypass_cache=bypass_cache)
    s.save()
    return jsonify(s.to_dict()), 201


@blueprint.route("/searches/<id>", methods=["GET"])
def get_search(id):
    bypass_cache = request.args.get("bypass_cache") == "true"
    search = get_existing_search(id)
    if not search:
        return jsonify({"error": "Search not found"}), 404
    
    if bypass_cache:
        # Reset all fields that would be reset in process_searches.py
        print(f"Resetting saved search {id} - bypass_cache == True", flush=True)
        search["results"] = None
        search["results_header"] = None
        search["meta"] = None
        search["is_ready"] = False
        search["is_completed"] = False
        search["backend_error"] = None
        search["timestamps"]["completed"] = None
        search["bypass_cache"] = True
        search["redshift_sql"] = Query(search["query"]).get_sql()
        redis_db.set(id, json.dumps(search))
        # Re-add to queue for processing
        print(f"Pushing {id} to search_queue", flush=True)
        redis_db.rpush(search_queue, id)
    
    return jsonify(search)


@blueprint.route("/results", methods=["GET", "POST"])
def results():
    """
    For testing OQL queries and results.
    """
    # set results from json
    raw_query = {
        "entity": request.json.get("get_rows"),
        "filter_works": request.json.get("filter_works"),
        "filter_aggs": request.json.get("filter_aggs"),
        "show_columns": request.json.get("show_columns"),
        "sort_by_column": request.json.get("sort_by_column"),
        "sort_by_order": request.json.get("sort_by_order"),
    }

    # query object
    query = Query(raw_query)

    raw_query = query.to_dict()
    # validate the query
    oqo = OQOValidator(all_entities_config)
    ok, error = oqo.validate(raw_query)

    if not ok:
        return jsonify({"invalid query error": error}), 400

    json_data = query.execute()

    # results table
    results_table = ResultTable(
        entity=query.entity,
        show_columns=query.show_columns,
        json_data=json_data,
        total_count=query.total_count,
        page=1,
        per_page=100,
    )
    results_table_response = results_table.response()
    result = {
        "query": query.to_dict(),
        "source": query.source,
        "results": results_table_response,
    }
    return jsonify(result)


def serve_config(data, filename):
    _format = request.args.get("format", "json")

    if _format.lower() in {'yaml', 'yml'}:
        yaml_config = yaml.dump(data, default_flow_style=False)
        response = make_response(yaml_config)
        response.headers['Content-Type'] = 'application/yaml'
        response.headers[
            'Content-Disposition'] = f'attachment; filename={filename}.yaml'
        return response
    else:
        return jsonify(data)


@blueprint.route("/entities/config", methods=["GET"])
def entities_config():
    return serve_config(all_entities_config, 'all_entities_config')


@blueprint.route("/entities/<entity>/config", methods=["GET"])
def entity_config(entity):
    if entity not in all_entities_config:
        return jsonify({"error": "Entity not found"}), 404

    return serve_config(all_entities_config[entity], f'{entity}_config')


@blueprint.route('/test_stories', methods=['POST'])
def create_testing_job():
    try:
        # If the content type is application/json, Flask should have already parsed it
        if request.is_json:
            j = request.json
        else:
            # If not, we'll try to parse it ourselves
            j = json.loads(request.data)

        if not j:
            return jsonify({'error': 'No tests provided'}), 400

        job_id = str(uuid.uuid4())

        # Create a new job in Redis
        job_data = {
            'status': 'queued',
            'timeout': j.get('timeout', 3 * 60),
            'tests': json.dumps(j['tests']),
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
