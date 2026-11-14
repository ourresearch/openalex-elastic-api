"""Does the works index's internal boolean still equal the public rule? (oxjob #2065)

The default works view hides `is_non_traditional_child: true` (core/default_view.py), which walden's
sync_works writes. It must be true on exactly the works the public rule names:

    has_parent_work:true AND is_traditional:false

This compares the two counts on the live index, and counts the works where they disagree each way.
They drift when TRADITIONAL_TYPES (core/work_type_classes.py) changes without a re-sync, or when a
sync writes one side without the other. Read-only: three counts on the works index.

    source ~/.zshenv && PYTHONPATH=. venv/bin/python scripts/check_default_view_fold.py

Exit 0 when the counts match and no work disagrees, 1 otherwise.
"""
import os
import sys

from elasticsearch import Elasticsearch

import settings
from core.default_view import HIDDEN_PIECE_FIELD, hidden_by_public_filters_query


def main():
    es = Elasticsearch(os.environ["ES_URL_WALDEN"], request_timeout=120)
    public = hidden_by_public_filters_query().to_dict()
    boolean = {"term": {HIDDEN_PIECE_FIELD: True}}

    def count(query):
        return es.count(index=settings.WORKS_INDEX, query=query)["count"]

    n_boolean = count(boolean)
    n_public = count(public)
    boolean_only = count({"bool": {"filter": [boolean], "must_not": [public]}})
    public_only = count({"bool": {"filter": [public], "must_not": [boolean]}})
    print(f"{HIDDEN_PIECE_FIELD}:true                               {n_boolean:>12,}")
    print(f"has_parent_work:true AND is_traditional:false (public)  {n_public:>12,}")
    print(f"boolean true, public rule false (hidden, should show)   {boolean_only:>12,}")
    print(f"public rule true, boolean not true (should be hidden)   {public_only:>12,}")
    ok = n_boolean == n_public and boolean_only == 0 and public_only == 0
    print("MATCH" if ok else "DRIFT: re-sync the boolean (walden notebooks/elastic/sync_works)")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
