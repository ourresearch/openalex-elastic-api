import json
from datetime import datetime, timezone
import os
import time

import redis
import sentry_sdk
from sentry_sdk.integrations.flask import FlaskIntegration

import settings
from app import create_app
from combined_config import all_entities_config
from oql.query import QueryNew
from oql.results_table import ResultTable
from oql.validate import OQOValidator

app = create_app()
redis_db = redis.Redis.from_url(settings.CACHE_REDIS_URL)
search_queue = "search_queue"

# enable sentry
sentry_sdk.init(
    dsn=os.environ.get("SENTRY_DSN"),
    integrations=[FlaskIntegration()]
)


def fetch_results(query):
    with app.app_context():
        # params
        entity = query.get("summarize_by") or "works"
        filters = query.get("filters") or []
        columns = query.get("return_columns")
        sort_by_column = query.get("sort_by", {}).get("column_id", "display_name")
        sort_by_order = query.get("sort_by", {}).get("direction", "asc")

        # validate the query
        oqo = OQOValidator(all_entities_config)
        ok, error = oqo.validate(query)

        if not ok:
            return {"invalid_query_error": error}

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
        return results_table_response


def process_searches():
    last_log_time = 0

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
        if search_json:
            print(f"found a search_json!")
        if not search_json:
            continue

        search = json.loads(search_json)
        if search.get("is_ready"):
            continue

        try:
            results = fetch_results(search["query"])

            if "invalid_query_error" in results:
                # invalid query
                search["invalid_query_error"] = results["invalid_query_error"]
                search["is_ready"] = True
                search["is_completed"] = True
                search["timestamps"]["completed"] = datetime.now(timezone.utc).isoformat()
            else:
                # valid results
                search["results"] = results["results"]
                search["results_header"] = results["results_header"]
                search["meta"] = results["meta"]
                search["is_ready"] = True
                search["is_completed"] = True
                search["timestamps"]["completed"] = datetime.now(timezone.utc).isoformat()
            print(f"Processed search {search_id} with {search}")
        except Exception as e:
            # backend error
            print(f"Error processing search {search_id}: {e}")
            search["backend_error"] = str(e)
            search["is_ready"] = True
            search["is_completed"] = True
            search["timestamps"]["completed"] = datetime.now(timezone.utc).isoformat()
            sentry_sdk.capture_exception(e)

        # save updated search object back to Redis
        print(f"Saving search {search_id} to redis with {search}")
        redis_db.set(search_id, json.dumps(search))

        # wait to avoid hammering the Redis server
        time.sleep(0.1)


if __name__ == "__main__":
    print(f"Processing searches from queue {search_queue}")
    process_searches()
