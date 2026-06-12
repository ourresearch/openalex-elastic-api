"""oxjob #450 Phase 2 — live identity check: the OQO `select` projection
(`execution.py` MessageSchema(only=…)) must project EXACTLY like the legacy
URL `?select=` path (`core.utils.process_only_fields`).

Boots the real app against live walden ES and compares, for each select set:
  legacy   GET /works?select=a,b,c&per_page=5
  OQO      GET /?oqo={"get_rows":"works","select":["a","b","c"],"per_page":5}
asserting: same status, same per-row key set (== the select set, in order),
same envelope keys, and meta.x_query present on both (since #378 it's emitted
on all entity responses, not just the execute path).

Run:
  source ~/.zshenv  # $ES_URL_WALDEN
  ELASTIC_URL=$ES_URL_WALDEN \
  REDSHIFT_SERVERLESS_URL=postgresql://u:p@localhost:5432/db \
  REDIS_DO_URL=redis://localhost:6379 REDISCLOUD_URL=redis://localhost:6379 \
  USERS_DB_URL=postgresql://u:p@localhost:5432/db \
  DATABASE_URL=postgresql://u:p@localhost:5432/db JWT_SECRET_KEY=x \
  PYTHONPATH=. venv/bin/python < scripts/oqo_select_projection_live_check.py
(run via stdin so sys.path[0] is the repo root — scripts/ids.py shadows `ids`.)
"""
import json
import urllib.parse

from app import create_app

CASES = [
    # (entity, select list) — mix registry-overlap and schema-only columns
    ("works", ["id", "display_name", "cited_by_count"]),
    ("works", ["id", "open_access", "authorships"]),  # schema-only nested
    ("authors", ["id", "display_name", "works_count"]),
    ("sources", ["id", "display_name", "issn"]),
]

app = create_app()
client = app.test_client()

failures = []
for entity, select in CASES:
    sel = ",".join(select)
    url_resp = client.get(f"/{entity}?select={sel}&per_page=5")
    url_body = url_resp.get_json() or {}

    oqo_dict = {"get_rows": entity, "select": select, "per_page": 5}
    encoded = urllib.parse.quote(json.dumps(oqo_dict))
    oqo_resp = client.get(f"/?oqo={encoded}")
    oqo_body = oqo_resp.get_json() or {}

    url_rows = url_body.get("results") or []
    oqo_rows = oqo_body.get("results") or []
    url_keys = [list(r.keys()) for r in url_rows]
    oqo_keys = [list(r.keys()) for r in oqo_rows]

    status_ok = url_resp.status_code == oqo_resp.status_code == 200
    rows_ok = bool(url_rows) and bool(oqo_rows)
    keys_ok = (
        all(k == select for k in url_keys) and all(k == select for k in oqo_keys)
    )
    env_url = sorted(url_body.keys())
    env_oqo = sorted(oqo_body.keys())
    envelope_ok = env_url == env_oqo
    xq_ok = "x_query" in (oqo_body.get("meta") or {}) and \
            "x_query" in (url_body.get("meta") or {})

    verdict = status_ok and rows_ok and keys_ok and envelope_ok and xq_ok
    print(f"{entity} select={sel}: url={url_resp.status_code} "
          f"oqo={oqo_resp.status_code} rows={len(url_rows)}/{len(oqo_rows)} "
          f"keys={'IDENTITY' if keys_ok else f'DIFF url={url_keys[:1]} oqo={oqo_keys[:1]}'} "
          f"envelope={'MATCH' if envelope_ok else f'DIFF {env_url} vs {env_oqo}'} "
          f"x_query(both)={'OK' if xq_ok else 'BAD'} "
          f"-> {'PASS' if verdict else 'FAIL'}")
    if not verdict:
        failures.append((entity, sel))
        if not status_ok:
            print("  url body:", json.dumps(url_body)[:300])
            print("  oqo body:", json.dumps(oqo_body)[:300])

print(f"\n{'ALL PASS' if not failures else f'FAILURES: {failures}'}")
raise SystemExit(0 if not failures else 1)
