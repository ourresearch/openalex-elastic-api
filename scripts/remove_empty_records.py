from elasticsearch_dsl import Q, Search, connections

import settings


def remove_empty():
    s = Search(index=settings.AUTHORS_INDEX)
    s = s.extra(size=10000)
    s = s.filter(~Q("exists", field="ids.openalex"))
    s = s.sort("id")
    print(f"Remaining: {s.count()}")
    response = s.execute()
    count = 0
    for r in response:
        count = count + 1
        doc_id = r.meta.id
        if not doc_id.startswith("https://openalex") and "cited_by_count" not in r:
            delete_from_elastic(r.meta.id)
    print(f"count: {count}")


def delete_from_elastic(record_id):
    s = Search(index=settings.AUTHORS_INDEX)
    s = s.filter("term", id=record_id)
    s.delete()
    print(f"deleted id {record_id}")


if __name__ == "__main__":
    connections.create_connection(hosts=[settings.ES_URL], timeout=30)
    connections.get_connection().indices.refresh(index=settings.AUTHORS_INDEX)
    for i in range(0, 10):
        print(f"iteration {i}")
        remove_empty()
        connections.get_connection().indices.refresh(index=settings.AUTHORS_INDEX)
