from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
import hashlib
import json
import copy
from typing import Dict, List, Optional

import redis
import requests

import settings

redis_db = redis.Redis.from_url(settings.CACHE_REDIS_URL or "redis://localhost:6379/0")

CACHE_EXPIRATION_MINUTES = 1
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

    def contains_user_data(self):
        """ Returns true if the query contains user data. """
        user_operators = [
            "matches any item in label",
            "matches every item in label"
        ]

        def does_filter_contain_user_data(filter_):
            if "filters" in filter_:
                return any(does_filter_contain_user_data(f) for f in filter_["filters"])
            return filter_.get("operator") in user_operators

        filters_to_check = (self.query.get("filter_works") or []) + (self.query.get("filter_aggs") or [])
        print(f"Checking filters: {filters_to_check}", flush=True)
        return any(does_filter_contain_user_data(f) for f in filters_to_check)
    
    def rewrite_query_with_user_data(self, user_id, jwt_token):
        """
        Recursively walk through the query and replace any filters that have label components
        with their equivalents that don't reference user labels.
        """
        def rewrite_filters(filters, case):
            """
            Recursive helper function to rewrite filters.
            case is either "filter_works" or "filter_aggs"
            """
            rewritten_filters = []
            for filter_obj in filters:
                if "join" in filter_obj and "filters" in filter_obj:
                    # Recursive case: rewrite the nested filters
                    rewritten_filter = {
                        "join": filter_obj["join"],
                        "filters": rewrite_filters(filter_obj["filters"], case),
                    }
                    rewritten_filters.append(rewritten_filter)
                else:
                    # Terminal case: check if the operator matches a label condition
                    operator = filter_obj.get("operator")
                    # print(f"looking at operator: {operator}")
                    if operator in ["matches any item in label", "matches every item in label"]:
                        print("Found user data in query")
                        label_id = filter_obj.get("value")
                        #label = Collection.get_collection_by_id(label_id)

                        headers = {"Authorization": jwt_token}
                        url = f"{settings.USERS_API_URL}/user/{user_id}/collections/{label_id}"
                        #print(f"Fetching label data from {url}")
                        response = requests.get(url, headers=headers)
                        label = response.json()

                        if not label:
                            raise ValueError(f"Label with ID {label_id} not found.")
                        if not label["ids"]:
                            raise ValueError(f"Label {label_id} contains no items.")

                        #print("Label Data:")
                        #print(label)

                        # Determine the join type based on the operator
                        join_type = "or" if operator == "matches any item in label" else "and"

                        works_id_keys = {
                            "authors": "authorships.author.id",
                            "continents": "authorships.institutions.continent",
                            "countries": "authorships.institutions.country",
                            "domains": "primary_topic.domain.id",
                            "fields": "primary_topic.field.id",
                            "funders": "grants.funder",
                            "institution-types": "authorships.institutions.type",
                            "institutions": "authorships.institutions.lineage",
                            "keywords": "keywords.id",
                            "langauges": "language",
                            "licenses": "MISSING",
                            "publishers": "MISSING",
                            "sdgs": "sustainable_developement_goals.id",
                            "sources": "primary_location.source.id",
                            "subfields": "primary_topic.subfield.id",
                            "topics": "primary_topic.id",
                            "work-types": "type",
                        }

                        column_id = works_id_keys[label.entity_type] if case == "filter_works" else "id"

                        # Construct the rewritten filters for this label
                        rewritten_label_filter = {
                            "join": join_type,
                            "filters": [
                                {
                                    "column_id": column_id,
                                    "value": id_value,
                                }
                                for id_value in label["ids"]
                            ],
                        }
                        rewritten_filters.append(rewritten_label_filter)
                    else:
                        rewritten_filters.append(filter_obj)

            return rewritten_filters

        # Start rewriting from self.query
        query_rewritten = copy.deepcopy(self.query)  # Create a copy of the original query

        for case in ["filter_works", "filter_aggs"]:
            if case in query_rewritten:
                query_rewritten[case] = rewrite_filters(query_rewritten[case], case)

        return query_rewritten

    def extract_filter_keys(self):
        """
        Extracts filter keys from both "filter_works" and "filter_aggs" into a flat list.
        """
        keys = []
        def walk_filters(filters, entity):
            for f in filters:
                # If this is a composite filter with a join and nested filters:
                if "join" in f and "filters" in f:
                    walk_filters(f["filters"], entity)
                else:
                    if "column_id" in f:
                        keys.append(f"{entity}.{f['column_id']}")

        for key in ["filter_works", "filter_aggs"]:
            key_type = "works" if key == "filter_works" else self.entity
            if key in self.query and isinstance(self.query[key], list):
                walk_filters(self.query[key], key_type)
        return keys if keys else None

    def contains_nested_boolean(self):
        """
        Returns true if the query contains nested boolean logic.
        """
        # For now, a simple check: if any filter has a "join" key, return True.
        for key in ["filter_works", "filter_aggs"]:
            if key in self.query and isinstance(self.query[key], list):
                for f in self.query[key]:
                    if "join" in f:
                        return True
        return False     

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


