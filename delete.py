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
        ids_to_delete = []
        for row in reader:
            if row["merge_from_id"] == last_id:
                last_id_seen = True
            if not last_id_seen:
                continue
            ids_to_delete.append(row["merge_from_id"])
            if len(ids_to_delete) == 100:
                s = Search(index=settings.WORKS_INDEX)
                s = s.filter("terms", id=ids_to_delete)
                s = s.extra(size=1000)
                s.delete()
                print(f"deleted {total} records")
                ids_to_delete.clear()
            total = total + 1

        if ids_to_delete:
            s = Search(index=settings.WORKS_INDEX)
            s = s.filter("terms", id=ids_to_delete)
            s.delete()
            print(f"deleted {total} records")


if __name__ == "__main__":
    connections.create_connection(hosts=[settings.ES_URL], timeout=30)
    delete_merged_works()
