from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
import hashlib
import json
from typing import Dict, List, Optional

import redis

import settings
from oql.query import Query

redis_db = redis.Redis.from_url(settings.CACHE_REDIS_URL or "redis://localhost:6379/0")

CACHE_EXPIRATION_MINUTES = 1


@dataclass
class Search:
    q: str
    id: str = field(init=False)
    results: Optional[List] = field(default_factory=list)
    meta: Optional[Dict] = field(default_factory=dict)
    is_ready: bool = False
    timestamp: str = field(init=False)

    def __post_init__(self):
        self.id = self.id_hash()
        self.timestamp = datetime.now(timezone.utc).isoformat()
        oql_format = get_oql_format(self.q)
        self.meta = {
            "q": self.q,
            "oql": oql_format["oql"],
            "is_valid": oql_format["is_valid"],
        }

    def id_hash(self) -> str:
        return hashlib.md5(self.q.encode()).hexdigest()

    def save(self):
        print(f"Saving search {self.id} to cache with {self.to_dict()}")
        redis_db.set(self.id, json.dumps(self.to_dict()))

    def to_dict(self):
        return asdict(self)


def is_cache_expired(search: Dict) -> bool:
    timestamp = datetime.fromisoformat(search["timestamp"])
    return datetime.now(timezone.utc) - timestamp > timedelta(
        minutes=CACHE_EXPIRATION_MINUTES
    )


def get_existing_search(id: str) -> Optional[Dict]:
    existing_search_json = redis_db.get(id)
    if not existing_search_json:
        return None
    existing_search = json.loads(existing_search_json)
    return existing_search


def get_oql_format(query_string: str) -> dict:
    q = Query(query_string)
    return {"is_valid": q.is_valid(), "oql": q.oql_query()}
