import csv
import gzip

from elasticsearch_dsl import Search, connections

import settings


def delete_merged_works():
    with gzip.open("merge-works.csv.gz", "rt") as f:
        reader = csv.DictReader(f)
        total = 0
        last_id = "https://openalex.org/W35623074"
        last_id_seen = False
        for row in reader:
            if row["merge_from_id"] == last_id:
                last_id_seen = True
            if not last_id_seen:
                continue
            id_to_delete = row["merge_from_id"]
            s = Search(index=settings.WORKS_INDEX)
            s = s.filter("term", id=id_to_delete)
            if s.count() < 5:
                print("deleting", id_to_delete)
                s.delete()
            total = total + 1
            print(f"deleted {total} records")


if __name__ == "__main__":
    connections.create_connection(hosts=[settings.ES_URL], timeout=30)
    delete_merged_works()
