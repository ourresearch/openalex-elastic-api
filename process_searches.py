import json
from datetime import datetime, timezone
import redis
import time

import settings
from app import create_app
from combined_config import all_entities_config
from oql.query import Query
from oql.results_table import ResultTable

app = create_app()
redis_db = redis.Redis.from_url(settings.CACHE_REDIS_URL)
search_queue = "search_queue"


def fetch_results(query_string):
    with app.app_context():
        query = Query(query_string, 1, 100)
        if query.is_valid():
            json_data = query.execute()
            entity = query.entity
            columns = query.columns
            columns = columns or all_entities_config[entity]["showOnTablePage"]
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
        else:
            results_table_response = {"meta": {}, "results": {}}
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
            results = fetch_results(search["q"])

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
