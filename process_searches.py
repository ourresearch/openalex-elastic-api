import json
from datetime import datetime, timezone
import redis
import time

import settings
from app import create_app
from combined_config import all_entities_config
from oql.query import QueryNew
from oql.results_table import ResultTable

app = create_app()
redis_db = redis.Redis.from_url(settings.CACHE_REDIS_URL)
search_queue = "search_queue"


def fetch_results(query):
    with app.app_context():
        # params
        entity = query.get("summarize_by") or "works"
        columns = query.get("return")
        sort_by_column = query.get("sort_by", {}).get("column_id", "display_name")
        sort_by_order = query.get("sort_by", {}).get("direction", "asc")

        # object
        query = QueryNew(
            entity=entity,
            columns=columns,
            filter_by=[],
            sort_by_column=sort_by_column,
            sort_by_order=sort_by_order,
        )

        json_data = query.execute()

        results_table = ResultTable(query, json_data)
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

            # update the search object
            search["results"] = results["results"]
            search["meta"] = results["meta"]
            search["is_ready"] = True
            search["timestamp"] = datetime.now(timezone.utc).isoformat()
            print(f"Processed search {search_id} with {search}")
        except Exception as e:
            print(f"Error processing search {search_id}: {e}")
            search["error"] = str(e)
            search["is_ready"] = True
            search["timestamp"] = datetime.now(timezone.utc).isoformat()

        # save updated search object back to Redis
        print(f"Saving search {search_id} to redis with {search}")
        redis_db.set(search_id, json.dumps(search))

        # wait to avoid hammering the Redis server
        time.sleep(0.1)


if __name__ == "__main__":
    print(f"Processing searches from queue {search_queue}")
    process_searches()
