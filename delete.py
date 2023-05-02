import csv
import gzip

from elasticsearch_dsl import Search, connections

import settings


def delete_merged_works():
    with gzip.open("merge-works.csv.gz", "rt") as f:
        reader = csv.DictReader(f)
        total = 0
        for row in reader:
            id_to_delete = row["merge_from_id"]
            find_id_and_delete(id_to_delete)
            total = total + 1
            print(f"deleted {total} records")
            break


def find_id_and_delete(id_to_delete):
    s = Search(index=settings.WORKS_INDEX)
    s = s.filter("term", id=id_to_delete)
    response = s.execute()
    for r in response:
        delete_from_elastic(r.id, r.meta.index)


def delete_from_elastic(id_to_delete, index):
    s = Search(index=index)
    s = s.filter("term", id=id_to_delete)
    s.delete()
    print(f"deleted id {id_to_delete} with index {index}")


if __name__ == "__main__":
    connections.create_connection(hosts=[settings.ES_URL], timeout=30)
    delete_merged_works()
