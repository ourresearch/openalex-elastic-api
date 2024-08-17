import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from oql.search_query_parameters import QueryParameters
from oql.util import from_dict
from oql.search import redis_db, CACHE_EXPIRATION_MINUTES, search_queue


@dataclass
class SearchV2:
    query_oql: str = ""
    query_params: QueryParameters = field(default_factory=QueryParameters)
    id: str = ""
    results: Optional[List] = field(default_factory=list)
    is_loading: bool = False
    timestamp: str = field(init=False)

    def __post_init__(self):
        self.timestamp = datetime.now(timezone.utc).isoformat()

    def save(self, enqueue=False):
        print(f"Saving search {self.id} to cache with {self.to_dict()}")
        redis_db.set(self.id, json.dumps(self.to_dict()))
        if enqueue:
            redis_db.rpush(search_queue, self.id)

    def to_dict(self):
        return asdict(self)

    def is_cache_expired(self) -> bool:
        timestamp = datetime.fromisoformat(self.timestamp)
        return datetime.now(timezone.utc) - timestamp > timedelta(
            minutes=CACHE_EXPIRATION_MINUTES
        )


def get_existing_search_v2(id: str) -> SearchV2 | None:
    existing_search_json = redis_db.get(id)
    if not existing_search_json:
        return None
    existing_search = json.loads(existing_search_json)
    s = from_dict(SearchV2, existing_search)
    return s


def update_existing_search_v2(id: str,
                              query_params: QueryParameters) -> SearchV2 | None:
    existing_search_json = redis_db.get(id)
    if not existing_search_json:
        return None
    existing_search_json = json.loads(existing_search_json)
    del existing_search_json['timestamp']
    s = from_dict(SearchV2, existing_search_json)
    s.query_params = query_params
    s.save()
    return s

