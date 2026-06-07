"""oxjob #363 — live Tier-3 parity check for cross-type `is in collection`
executed on the OQO-native path (`GET /?oqo=…`) vs the rendered URL path.

Before #363 the OQO execution path read a bare `col_…` on a cross-type entity
field as a literal OpenAlex ID and matched ~zero; only the rendered-URL pre-pass
(`core/filter._apply_cross_type_collection_filters`) resolved it. This boots the
real app (live walden ES + prod users-api) and asserts both paths now return the
same member-derived count for a real Jason-owned authors collection.

Run:
  source ~/.zshenv  # for $ES_URL_WALDEN
  USERS_API_URL=https://user.openalex.org \
  REDSHIFT_SERVERLESS_URL=postgresql://u:p@localhost:5432/db \
  REDIS_DO_URL=redis://localhost:6379 REDISCLOUD_URL=redis://localhost:6379 \
  USERS_DB_URL=postgresql://u:p@localhost:5432/db \
  DATABASE_URL=postgresql://u:p@localhost:5432/db JWT_SECRET_KEY=x \
  PYTHONPATH=. venv/bin/python scripts/oqo_cross_type_collection_live_check.py
"""
import json
import urllib.parse

from app import create_app

# Jason-owned authors collection (12 authors → 585 works at fixture time, #363).
COLLECTION_ID = "col_a48SaZFvdS"
FIELD = "authorships.author.id"
# Prod api_key (Jason); forwarded to users-api so the owner check passes and the
# collection resolves to its 12 author IDs.
API_KEY = "tEO76RnvV2LwjHcTG74OtA"

app = create_app()
client = app.test_client()
auth = {"Authorization": f"Bearer {API_KEY}"}

# 1. Rendered-URL path (the pre-pass resolves col_).
url_resp = client.get(f"/works?filter={FIELD}:{COLLECTION_ID}", headers=auth)
url_body = url_resp.get_json() or {}
url_count = url_body.get("meta", {}).get("count")
print(f"rendered-URL  /works?filter={FIELD}:{COLLECTION_ID} -> "
      f"{url_resp.status_code}  count={url_count}")

# 2. OQO-native path (the new resolver in oqo_to_es._cross_type_collection_query).
oqo_dict = {
    "get_rows": "works",
    "filter_rows": [
        {"column_id": FIELD, "value": COLLECTION_ID, "operator": "in collection"}
    ],
}
# Execution lives at the root (`GET /?oqo=…`); `/query/oqo/...` only translates.
encoded = urllib.parse.quote(json.dumps(oqo_dict))
oqo_resp = client.get(f"/?oqo={encoded}", headers=auth)
oqo_body = oqo_resp.get_json() or {}
oqo_count = oqo_body.get("meta", {}).get("count")
print(f"OQO-native    /query/oqo (author is in collection) -> "
      f"{oqo_resp.status_code}  count={oqo_count}")
if oqo_resp.status_code != 200:
    print("  body:", json.dumps(oqo_body)[:600])

print(f"\nTier-3 parity: url={url_count} oqo={oqo_count} -> "
      f"{'MATCH' if url_count == oqo_count and url_count else 'DIFF'}")
