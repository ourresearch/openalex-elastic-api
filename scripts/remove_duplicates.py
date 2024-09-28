from elasticsearch_dsl import Q, Search, connections
from elasticsearch.exceptions import ConflictError

from settings import ES_URL, WORKS_INDEX


def remove_duplicates():
    """Find and remove duplicates from works index."""
    count = 0
    with open("duplicate_record_ids_works.csv", "r") as f:
        for line in f:
            count += 1
            print(f"processing line {count}")
            work_id = line.strip()
            find_id_and_delete(work_id)


def find_id_and_delete(work_id):
    s = Search(index=WORKS_INDEX)
    formatted_id = f"https://openalex.org/{work_id}"
    s = s.filter("term", id=formatted_id)
    s = s.sort("-@timestamp")
    response = s.execute()
    if s.count() == 2:
        record = response.hits[1]
        delete_from_elastic(record.id, record.meta.index)


def delete_from_elastic(duplicate_id, index):
    s = Search(index=index)
    s = s.filter("term", id=duplicate_id)
    # handle conflict error
    try:
        response = s.delete()
    except ConflictError as e:
        print(f"Already deleted id {duplicate_id}")
    else:
        print(f"deleted id {duplicate_id} with index {index}")


if __name__ == "__main__":
    connections.create_connection(hosts=[ES_URL], timeout=30)
    remove_duplicates()
