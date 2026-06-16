"""oxjob #363 — live Tier-3 parity check for semantic (vector) search executed
on the OQO-native path (`GET /?oqo=…`) vs the legacy URL path
(`GET /works?search.semantic=…`).

Case 30 fixed only the OQO→URL *render* direction. Executing the same query as
an OQO (`/?oqo=…` with a `*.search.semantic` leaf) used to silently run a plain
single-pass match — the OQO execution path never routed to the two-phase vector
index. This boots the real app (live walden ES + vector index + Databricks
embeddings) and asserts both paths now return the SAME ordered result IDs.

Run (USE_VECTOR_INDEX + vector ES URL + Databricks embedding creds required —
pull them from the elastic-api Heroku config):
  source ~/.zshenv  # $ES_URL_WALDEN
  USE_VECTOR_INDEX=true \
  ES_VECTOR_SEARCH_URL=... DATABRICKS_HOST=... \
  DATABRICKS_OAUTH_CLIENT_ID=... DATABRICKS_OAUTH_SECRET=... DATABRICKS_OAUTH_TOKEN_URL=... \
  REDSHIFT_SERVERLESS_URL=postgresql://u:p@localhost:5432/db \
  REDIS_DO_URL=redis://localhost:6379 REDISCLOUD_URL=redis://localhost:6379 \
  USERS_DB_URL=postgresql://u:p@localhost:5432/db \
  DATABASE_URL=postgresql://u:p@localhost:5432/db JWT_SECRET_KEY=x \
  PYTHONPATH=. venv/bin/python scripts/oqo_semantic_live_check.py
"""
import json
import urllib.parse

from app import create_app

QUERY = "graph neural networks for molecular property prediction"

app = create_app()
client = app.test_client()


def _ids(body):
    return [r.get("id") for r in (body.get("results") or [])]


# 1. Legacy URL path — the live vector path (verified working in Case 30).
url_resp = client.get(
    "/works?search.semantic=" + urllib.parse.quote(QUERY) + "&per_page=10"
)
url_body = url_resp.get_json() or {}
url_count = url_body.get("meta", {}).get("count")
url_ids = _ids(url_body)
print(f"legacy URL  /works?search.semantic=… -> {url_resp.status_code}  "
      f"count={url_count}  top={url_ids[:3]}")
if url_resp.status_code != 200:
    print("  body:", json.dumps(url_body)[:600])

# 2. OQO-native path — the new routing in execution._execute_semantic_oqo.
oqo_dict = {
    "get_rows": "works",
    "filter_rows": [
        {"column_id": "abstract.search.semantic", "value": QUERY,
         "operator": "has"}
    ],
    "per_page": 10,
}
encoded = urllib.parse.quote(json.dumps(oqo_dict))
oqo_resp = client.get(f"/?oqo={encoded}")
oqo_body = oqo_resp.get_json() or {}
oqo_count = oqo_body.get("meta", {}).get("count")
oqo_ids = _ids(oqo_body)
print(f"OQO-native  /?oqo=(abstract is similar to …) -> {oqo_resp.status_code}  "
      f"count={oqo_count}  top={oqo_ids[:3]}")
if oqo_resp.status_code != 200:
    print("  body:", json.dumps(oqo_body)[:600])

same_count = url_count == oqo_count and url_count is not None
same_ids = url_ids == oqo_ids and bool(url_ids)
print(f"\nTier-3 parity: count {url_count}=={oqo_count} -> "
      f"{'MATCH' if same_count else 'DIFF'};  "
      f"ordered IDs -> {'MATCH' if same_ids else 'DIFF'}")
