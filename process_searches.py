import json
from datetime import datetime, timezone
import os
import time
import hashlib
import traceback

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

# enable sentry
sentry_sdk.init(
    dsn=os.environ.get("SENTRY_DSN"),
    integrations=[FlaskIntegration()]
)


def fetch_results(query):
    with app.app_context():
        # params
        entity = query.get("get_rows")
        filter_works = query.get("filter_works")
        filter_aggs = query.get("filter_aggs")
        show_columns = query.get("show_columns")
        sort_by_column = query.get("sort_by_column")
        sort_by_order = query.get("sort_by_order")

        # query object
        query = Query(
            entity=entity,
            filter_works=filter_works,
            filter_aggs=filter_aggs,
            show_columns=show_columns,
            sort_by_column=sort_by_column,
            sort_by_order=sort_by_order,
        )

        json_data = query.execute()

        # results table
        results_table = ResultTable(
            entity=entity,
            show_columns=show_columns,
            json_data=json_data,
            total_count=query.total_count,
            page=1,
            per_page=100,
        )
        results_table_response = results_table.response()
        results_table_response["source"] = query.source
        return results_table_response


def process_searches():
    last_log_time = 0
    cache_expiration = 24 * 3600  # 24 hours in seconds

    while True:
        search_id = redis_db.lpop(search_queue)
        if not search_id:
            current_time = time.time()
            if current_time - last_log_time >= 60:
                print(f"Waiting for searches from queue {search_queue}")
                last_log_time = current_time

            time.sleep(0.1)
            continue

        search_json = redis_db.get(search_id)
        if not search_json:
            continue

        search = json.loads(search_json)

        # Check if bypass_cache is set to true or the cache is older than 24 hours
        bypass_cache = search.get("bypass_cache", False)
        print(f"Processing search {search_id} with bypass_cache={bypass_cache}")
        last_processed_time = search["timestamps"].get("completed")

        if last_processed_time:
            last_processed_time = datetime.fromisoformat(last_processed_time)
            time_since_processed = (datetime.now(timezone.utc) - last_processed_time).total_seconds()
        else:
            time_since_processed = cache_expiration + 1  # force recalculation if no timestamp

        # cache_valid = not bypass_cache and time_since_processed <= cache_expiration
        # turn off caching for now
        cache_valid = False

        # If the cache is not valid or bypass_cache is true, clear old results and reset state
        if not cache_valid:
            print(f"Cache is not valid for search {search_id}")
            search["results"] = None
            search["results_header"] = None
            search["meta"] = None
            search["is_ready"] = False
            search["is_completed"] = False
            search["backend_error"] = None
            search["timestamps"]["completed"] = None

            # Save the cleared search object back to Redis
            print(f"Clearing old results for search {search_id}")
            redis_db.set(search_id, json.dumps(search))

        # process only if results are not ready or the cache is invalid (bypass or older than 24 hours)
        if search.get("is_ready") and cache_valid:
            print(f"Search {search_id} is already processed and cache is valid so skipping")
            continue

        try:
            results = fetch_results(search["query"])

            if "invalid_query_error" in results:
                # invalid query
                search["invalid_query_error"] = results["invalid_query_error"]
                search["is_ready"] = True
                search["is_completed"] = True            
            else:
                # valid results
                search["results"] = results["results"]
                search["results_header"] = results["results_header"]
                search["meta"] = results["meta"]
                search["source"] = results["source"]
                search["is_ready"] = True
                search["is_completed"] = True

            # timestamps
            completed = datetime.now(timezone.utc)
            started = datetime.fromisoformat(search["timestamps"]["started"])
            duration = (completed - started).total_seconds()
            search["timestamps"]["completed"] = completed.isoformat()
            search["timestamps"]["duration"] = duration

            print(f"Processed search {search_id}")
        except Exception as e:
            # backend error
            tb = traceback.extract_tb(e.__traceback__)
            for frame in tb:
                error_msg = f"Error: {e}, File: {frame.filename}, Line: {frame.lineno}, Function: {frame.name}"

            print(error_msg)
            search["backend_error"] = error_msg
            search["is_ready"] = True
            search["is_completed"] = True
            search["timestamps"]["completed"] = datetime.now(timezone.utc).isoformat()
            sentry_sdk.capture_exception(e)

        # save updated search object back to Redis
        print(f"Saving search {search_id} to redis")
        redis_db.set(search_id, json.dumps(search))

        # wait to avoid hammering the Redis server
        time.sleep(0.1)


def generate_cache_key(query_dict):
    query_str = json.dumps(query_dict, sort_keys=True)
    return hashlib.md5(query_str.encode('utf-8')).hexdigest()


if __name__ == "__main__":
    print(f"Processing searches from queue {search_queue}")
    process_searches()
