import hashlib
import json
from typing import Dict, List, Optional
from dataclasses import asdict, dataclass, field
import redis

import settings

redis_db = redis.Redis.from_url(settings.CACHE_REDIS_URL or "redis://localhost:6379/0", decode_responses=True)
search_queue = settings.SEARCH_QUEUE


@dataclass
class Search:
    id: str = field(init=False)
    query: dict = field(default_factory=dict)
    submitted_query: Optional[dict] = None
    results: Optional[List] = field(default_factory=list)
    results_header: Optional[List] = field(default_factory=list)
    meta: Optional[Dict] = field(default_factory=dict)
    is_completed: bool = False
    is_ready: bool = False
    bypass_cache: bool = not settings.ENABLE_SEARCH_CACHE
    timestamps: Dict[str, str] = field(default_factory=dict)
    backend_error: Optional[str] = None
    source: Optional[str] = None
    redshift_sql: Optional[str] = None
    oql: Optional[str] = None
    attempts: int = 0

    def __post_init__(self):
        self.id = self.hash_id()

    def hash_id(self):
        query_str = json.dumps(self.query, sort_keys=True)
        return hashlib.md5(query_str.encode('utf-8')).hexdigest()

    def save(self):
        print(f"Saving search {self.id} to cache")
        redis_db.set(self.id, json.dumps(asdict(self)))
        # add to queue for processing
        redis_db.rpush(search_queue, self.id)

    def to_dict(self):
        d = asdict(self)
        if self.submitted_query is not None:
            d["query"] = self.submitted_query
        return d

    @classmethod
    def from_dict(cls, d):
        d = dict(d)
        id_val = d.pop("id", None)
        obj = cls(**d)
        if id_val is not None:
            obj.id = id_val
        return obj

    @classmethod
    def get(cls, id: str) -> Optional["Search"]:
        existing_search_json = redis_db.get(id)
        if not existing_search_json:
            return None
        existing_search = json.loads(existing_search_json)
        return cls.from_dict(existing_search)


