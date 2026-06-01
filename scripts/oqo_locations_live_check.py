"""oxjob #334 — live round-trip check for /locations through the OQO /query path.

Boots the real app (live walden ES) and exercises:
  1. legacy  GET /locations?per-page=5
  2. OQO     GET /query  with the URL-derived OQO for the same locations request
Both must return 200 with results; before the fix (2) returned 400 invalid_entity.
"""
import json
from app import create_app

app = create_app()
client = app.test_client()

# 1. Legacy list endpoint.
legacy = client.get("/locations?per-page=5")
print("legacy /locations            ->", legacy.status_code)

# 2. Execute the equivalent OQO via GET /query/oqo/<urlencoded-json>.
import urllib.parse

oqo_dict = {"get_rows": "locations", "per_page": 5}
encoded = urllib.parse.quote(json.dumps(oqo_dict))
resp = client.get(f"/query/oqo/{encoded}")
print("OQO     /query/oqo (locations) ->", resp.status_code)

body = resp.get_json() or {}
if resp.status_code != 200:
    print("  body:", json.dumps(body)[:500])
else:
    meta = body.get("meta", {})
    print("  meta.count:", meta.get("count"), " results:", len(body.get("results", [])))

legacy_count = (legacy.get_json() or {}).get("meta", {}).get("count")
oqo_count = body.get("meta", {}).get("count")
print(f"\ncount parity: legacy={legacy_count} oqo={oqo_count} ->",
      "MATCH" if legacy_count == oqo_count else "DIFF")
