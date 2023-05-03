from elasticsearch import Elasticsearch
from elasticsearch_dsl import Q, Search, connections

import settings

"""
Run with: python -m scripts.modify_fields
"""


def alter_records():
    es = Elasticsearch([settings.ES_URL], timeout=30)
    s = Search(index=settings.PUBLISHERS_INDEX)
    s = s.extra(size=10000)
    s = s.filter(Q("exists", field="parent_publisher"))
    print(f"Remaining: {s.count()}")
    response = s.execute()
    count = 0
    for r in response:
        count = count + 1
        r.parent_publisher = None
        doc = r.to_dict()
        # index the record to replace the existing one
        es.index(index=r.meta.index, id=r.id, document=doc)
        # refresh the index
        print(f"Updated: {r.id}")
    es.indices.refresh(index=settings.PUBLISHERS_INDEX)
    print(f"count: {count}")


if __name__ == "__main__":
    connections.create_connection(hosts=[settings.ES_URL], timeout=30)
    alter_records()
