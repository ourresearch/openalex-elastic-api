from elasticsearch_dsl import Q, Search, connections

from settings import ES_URL, WORKS_INDEX


def remove_duplicates():
    """Find and remove duplicates from works index."""
    count = 0
    # initial run
    s = Search(index="duplicated-ids-full")
    s = s.extra(size=200)
    s = s.extra(search_after=["https://openalex.org/W3199998869"])
    s = s.sort("id")
    kwargs = {"ids.openalex.value_count": {"gt": 1}}
    q = Q("range", **kwargs)
    s = s.filter(q)
    response = s.execute()
    for r in response:
        id = r.id
        find_id_and_delete(id)
        count = count + 1
    search_after = id

    while search_after:
        s = Search(index="duplicated-ids-full")
        s = s.extra(size=200)
        s = s.extra(search_after=[search_after])
        s = s.sort("id")
        kwargs = {"ids.openalex.value_count": {"gt": 1}}
        q = Q("range", **kwargs)
        s = s.filter(q)
        response = s.execute()
        for r in response:
            id = r.id
            find_id_and_delete(id)
            count = count + 1
            print(f"count: {count}")
        search_after = id


def find_id_and_delete(id):
    s = Search(index=WORKS_INDEX)
    s = s.filter("term", id=id)
    s = s.sort("-@timestamp")
    response = s.execute()
    if s.count() == 2:
        record = response.hits[1]
        delete_from_elastic(record.id, record.meta.index)


def delete_from_elastic(duplicate_id, index):
    s = Search(index=index)
    s = s.filter("term", id=duplicate_id)
    response = s.delete()
    print(f"deleted id {duplicate_id} with index {index}")


if __name__ == "__main__":
    connections.create_connection(hosts=[ES_URL], timeout=30)
    remove_duplicates()
