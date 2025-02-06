import json
import time
import hashlib
import traceback
import os
import concurrent.futures
from datetime import datetime, timezone

import redis
import sentry_sdk
from sentry_sdk.integrations.flask import FlaskIntegration

import settings
from app import create_app
from combined_config import all_entities_config
from oql.query import Query
from oql.results_table import ResultTable
from oql.validate import OQOValidator

app = create_app()
redis_db = redis.Redis.from_url(settings.CACHE_REDIS_URL)
search_queue = settings.SEARCH_QUEUE

# Enable Sentry
sentry_sdk.init(
    dsn=os.environ.get("SENTRY_DSN"),
    integrations=[FlaskIntegration()]
)


def fetch_results(query):
    with app.app_context():
        entity = query.get("get_rows")
        filter_works = query.get("filter_works")
        filter_aggs = query.get("filter_aggs")
        show_columns = query.get("show_columns")
        sort_by_column = query.get("sort_by_column")
        sort_by_order = query.get("sort_by_order")

        query_obj = Query(
            entity=entity,
            filter_works=filter_works,
            filter_aggs=filter_aggs,
            show_columns=show_columns,
            sort_by_column=sort_by_column,
            sort_by_order=sort_by_order,
        )

        json_data = query_obj.execute()

        results_table = ResultTable(
            entity=entity,
            show_columns=show_columns,
            json_data=json_data,
            total_count=query_obj.total_count,
            page=1,
            per_page=100,
        )
        results_table_response = results_table.response()
        results_table_response["source"] = query_obj.source

        return results_table_response


def process_search(search_id):
    search_json = redis_db.get(search_id)
    if not search_json:
        return

    search = json.loads(search_json)
    bypass_cache = search.get("bypass_cache", False)
    print(f"Processing search {search_id} with bypass_cache={bypass_cache}", flush=True)
    
    cache_expiration = 24 * 3600  # 24 hours in seconds
    last_processed_time = search["timestamps"].get("completed")
    if last_processed_time:
        last_processed_time = datetime.fromisoformat(last_processed_time)
        time_since_processed = (datetime.now(timezone.utc) - last_processed_time).total_seconds()
    else:
        time_since_processed = cache_expiration + 1  # Force recalculation if no timestamp

    cache_valid = settings.ENABLE_SEARCH_CACHE and not bypass_cache and time_since_processed <= cache_expiration

    if not cache_valid:
        print(f"Cache is not valid for search {search_id}", flush=True)
        search["results"] = None
        search["results_header"] = None
        search["meta"] = None
        search["is_ready"] = False
        search["is_completed"] = False
        search["backend_error"] = None
        search["timestamps"] = {}
        print(f"Clearing old results for search {search_id}", flush=True)
        redis_db.set(search_id, json.dumps(search))

    if search.get("is_ready") and cache_valid:
        print(f"Search {search_id} is already processed and cache is valid, skipping", flush=True)
        return

    try:
        print(f"Executing query {search['id']}", flush=True)
        results = fetch_results(search["query"])
        print(f"--- using {results['source']}", flush=True)

        if "invalid_query_error" in results:
            search["invalid_query_error"] = results["invalid_query_error"]
        else:
            search["results"] = results["results"]
            search["results_header"] = results["results_header"]
            search["meta"] = results["meta"]
            search["source"] = results["source"]

        search["is_ready"] = True
        search["is_completed"] = True

        search["timestamps"] = results["timestamps"]
        started = datetime.fromisoformat(search["timestamps"]["started"])
        completed = datetime.fromisoformat(search["timestamps"]["completed"])
        duration = (completed - started).total_seconds()
        search["timestamps"]["duration"] = duration

        if "core_query_completed" in search["timestamps"]:
            core_completed = datetime.fromisoformat(search["timestamps"]["core_query_completed"])
            secondary_completed = datetime.fromisoformat(search["timestamps"]["secondary_queries_completed"])
            duration_core = (core_completed - started).total_seconds()
            duration_secondary = (secondary_completed - core_completed).total_seconds()
            search["timestamps"]["duration_core"] = duration_core
            search["timestamps"]["duration_secondary"] = duration_secondary
            search["timestamps"]["duration_core_percent"] = duration_core / (duration_core + duration_secondary)

        print(f"Processed search {search_id}", flush=True)

    except Exception as e:
        tb = traceback.extract_tb(e.__traceback__)
        for frame in tb:
            error_msg = f"Error: {e}, File: {frame.filename}, Line: {frame.lineno}, Function: {frame.name}"
        print(error_msg, flush=True)
        search["backend_error"] = error_msg
        search["is_ready"] = True
        search["is_completed"] = True
        search["results"] = None
        search["results_header"] = None
        search["meta"] = None
        sentry_sdk.capture_exception(e)

    print(f"Saving search {search_id} to Redis", flush=True)
    redis_db.set(search_id, json.dumps(search))
    time.sleep(0.1)  # Small delay to avoid hammering Redis too quickly


def process_searches_concurrently(max_workers=100):
    """
    Continuously pulls search IDs from the Redis queue and processes them concurrently.
    """
    last_log_time = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor: 
        while True:
            search_id = redis_db.lpop(search_queue)
            if not search_id:
                current_time = time.time()
                if current_time - last_log_time >= 60:
                    print(f"Waiting for searches from queue {search_queue}", flush=True)
                    last_log_time = current_time
                time.sleep(0.1)
                continue

            executor.submit(process_search, search_id)


def generate_cache_key(query_dict):
    query_str = json.dumps(query_dict, sort_keys=True)
    return hashlib.md5(query_str.encode('utf-8')).hexdigest()


if __name__ == "__main__":
    print(f"Processing searches from queue {search_queue}", flush=True)
    process_searches_concurrently(max_workers=10)