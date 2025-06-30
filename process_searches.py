import json
import time
import traceback
import os
import concurrent.futures
from datetime import datetime, timezone

import redis
import sentry_sdk
from sentry_sdk.integrations.flask import FlaskIntegration

from settings import SEARCH_QUEUE, ENABLE_SEARCH_CACHE, CACHE_REDIS_URL
from app import create_app
from oql.query import Query
from oql.results_table import ResultTable
from oql.search_log import update_search_logs

app = create_app()
redis_db = redis.Redis.from_url(CACHE_REDIS_URL, decode_responses=True)

# Enable Sentry
sentry_sdk.init(
    dsn=os.environ.get("SENTRY_DSN"),
    integrations=[FlaskIntegration()]
)


def process_search(search_id):
    search_json = redis_db.get(search_id)
    if not search_json:
        return

    search = json.loads(search_json)
    print(f"Processing search {search_id}", flush=True)
    #print(f"Query {search['query']}", flush=True)

    cache_valid = is_cache_valid(search)
    if not cache_valid:
        search = clear_search_cache(search)
    #print(f"Cache valid: {cache_valid}", flush=True)

    if search.get("is_ready") and cache_valid:
        print(f"Search {search_id} is already processed and cache is valid, skipping", flush=True)
        return

    try:
        print(f"Executing query {search['id']}", flush=True)
        results = fetch_results(search["query"])

        if "invalid_query_error" in results:
            search["invalid_query_error"] = results["invalid_query_error"]
        else:
            print(f"Results received for {search['id']}", flush=True)
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
            duration_core = (core_completed - started).total_seconds()
            search["timestamps"]["duration_core"] = duration_core

        #print(f"Processed search {search_id}", flush=True)

    except Exception as e:
        tb = traceback.extract_tb(e.__traceback__)
        error_frames = []
        for frame in tb:
            error_frames.append(f"File: {frame.filename}, Line: {frame.lineno}, Function: {frame.name}")
        
        error_msg = f"Error: {e}\nTraceback:\n" + "\n".join(error_frames)
        print(error_msg, flush=True)

        # Check if it's a connection error and handle retries
        print(f"Debug - Error string: {str(e)}", flush=True)
        if any(error in str(e) for error in ("ConnectionError", "ConnectionTimeout", "OperationalError")):
            attempts = search.get("attempts", 0) + 1
            search["attempts"] = attempts
            
            if attempts < 3:  # Maximum 3 retry attempts
                print(f"Connection error, retrying search {search_id} (attempt {attempts})", flush=True)
                redis_db.rpush(SEARCH_QUEUE, search_id)
                redis_db.set(search_id, json.dumps(search))
                return
            else:
                error_msg = f"Failed after {attempts} attempts. Error: {error_msg}"

        search["backend_error"] = error_msg
        search["is_ready"] = True
        search["is_completed"] = True
        search["results"] = None
        search["results_header"] = None
        search["meta"] = None
        sentry_sdk.capture_exception(e)

    #print(f"Saving search {search_id} to Redis", flush=True)
    redis_db.set(search_id, json.dumps(search))
    update_search_logs(search_id, search)
    time.sleep(0.1)  # Small delay to avoid hammering Redis too quickly


def fetch_results(query):
    with app.app_context():
        query_obj = Query(query)
        json_data = query_obj.execute()

        results_table = ResultTable(
            entity=query_obj.entity if not query_obj.show_underlying_works else "works",
            show_columns=query_obj.show_columns,
            json_data=json_data,
            total_count=query_obj.total_count,
            works_count=query_obj.works_count,
            page=1,
            per_page=100,
        )
        results_table_response = results_table.response()
        results_table_response["source"] = query_obj.source

        return results_table_response


def is_cache_valid(search):
    CACHE_EXPIRATION = 24 * 3600  # 24 hours in seconds
    bypass_cache = search.get("bypass_cache", False)
    last_processed_time = search["timestamps"].get("completed")
    if last_processed_time:
        last_processed_time = datetime.fromisoformat(last_processed_time)
        time_since_processed = (datetime.now(timezone.utc) - last_processed_time).total_seconds()
    else:
        time_since_processed = CACHE_EXPIRATION + 1  # Force recalculation if no timestamp
    cache_valid = ENABLE_SEARCH_CACHE and not bypass_cache and time_since_processed <= CACHE_EXPIRATION
    
    return cache_valid


def clear_search_cache(search):
    #print(f"Cache is not valid for search {search['id']}", flush=True)
    search["results"] = None
    search["results_header"] = None
    search["meta"] = None
    search["is_ready"] = False
    search["is_completed"] = False
    search["backend_error"] = None
    search["attempts"] = 0
    search["timestamps"] = {}
    with app.app_context():
        search["redshift_sql"] = Query(search["query"]).get_sql()
    redis_db.set(search["id"], json.dumps(search))
    return search


def process_searches_concurrently(max_workers=100):
    """
    Continuously pulls search IDs from the Redis queue and processes them concurrently.
    """
    last_log_time = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor: 
        while True:
            search_id = redis_db.lpop(SEARCH_QUEUE)
            if not search_id:
                current_time = time.time()
                if current_time - last_log_time >= 60:
                    print(f"Waiting for searches from queue {SEARCH_QUEUE}", flush=True)
                    last_log_time = current_time
                time.sleep(0.1)
                continue

            executor.submit(process_search, search_id)


if __name__ == "__main__":
    process_searches_concurrently(max_workers=10)