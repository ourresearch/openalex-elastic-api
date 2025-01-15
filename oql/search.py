from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
import hashlib
import json
from typing import Dict, List, Optional

import redis

import settings

redis_db = redis.Redis.from_url(settings.CACHE_REDIS_URL or "redis://localhost:6379/0")

CACHE_EXPIRATION_MINUTES = 1
search_queue = "search_queue"


@dataclass
class Search:
    id: str = field(init=False)
    query: dict = field(default_factory=dict)
    results: Optional[List] = field(default_factory=list)
    results_header: Optional[List] = field(default_factory=list)
    meta: Optional[Dict] = field(default_factory=dict)
    is_completed: bool = False
    is_ready: bool = False
    bypass_cache: bool = True
    timestamps: Dict[str, str] = field(default_factory=dict)
    source: Optional[str] = None

    def __post_init__(self):
        self.id = self.hash_id()
        self.timestamps["started"] = datetime.now(timezone.utc).isoformat()
        self.timestamps["est_completed"] = "not implemented"

    def hash_id(self):
        query_str = json.dumps(self.query, sort_keys=True)
        return hashlib.md5(query_str.encode('utf-8')).hexdigest()

    def save(self):
        print(f"Saving search {self.id} to cache")
        redis_db.set(self.id, json.dumps(self.to_dict()))
        # add to queue for processing
        redis_db.rpush(search_queue, self.id)

    def to_dict(self):
        return asdict(self)


def get_existing_search(id: str) -> Optional[Dict]:
    existing_search_json = redis_db.get(id)
    if not existing_search_json:
        return None
    existing_search = json.loads(existing_search_json)
    return existing_search
