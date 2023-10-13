import os
from elasticsearch_dsl import Search, connections

from deepdiff import DeepDiff
import requests


def test_urls():
    """"
    Get recent api request urls from openalex-api-usage, then test to see if dev is the same as prod
    """
    s = Search(index="openalex-heroku-logs-2023.09.2*")
    s = s.extra(size=100)
    s = s.sort("-@timestamp")
    records = s.execute()
    for r in records:
        if r.request_path.endswith("/ngrams") or "api_key" in r.request_path:
            continue
        compare_responses(r.request_path)


def compare_responses(path):
    r1 = requests.get(f"https://api.openalex.org{path}")
    r2 = requests.get(f"http://127.0.0.1:5000{path}")
    response1 = r1.json()
    response2 = r2.json()
    print(f"comparing {path}")
    # delete dictionary item meta -> db_response_time_ms
    if "meta" in response1 or "meta" in response2:
        del response1["meta"]["db_response_time_ms"]
        del response2["meta"]["db_response_time_ms"]
    if response1 == response2:
        print(f"OK: {path}")
    elif "meta" in response1 and "meta" in response2:
        # ensure count is within 1% of each other
        if response1["meta"]["count"] - response2["meta"]["count"] < 0.01 * response1["meta"]["count"]:
            print(f"OK: {path}")
    else:
        print(DeepDiff(response1, response2))
        print(f"ERROR: {path}")


if __name__ == "__main__":
    connections.create_connection(hosts=[os.getenv("ES_API_USAGE")], timeout=30)
    test_urls()
