import csv
import gzip

from elasticsearch import Elasticsearch
from elasticsearch.helpers import bulk

import settings


def add_merged_works():
    es = Elasticsearch([settings.ES_URL_WALDEN], timeout=30)
    # open csv with gzip
    with gzip.open("merge-works.csv.gz", "rt") as f:
        reader = csv.DictReader(f)
        records = []
        total = 0
        for row in reader:
            record = {
                "_index": "merge-works",
                "_id": row["merge_from_id"],
                "_source": {
                    "id": row["merge_from_id"],
                    "merge_into_id": row["merge_into_id"],
                },
            }
            records.append(record)
            total = total + 1

            if len(records) % 10000 == 0:
                print(f"indexing {len(records)} records out of {total}")
                bulk(es, records)
                print(f"last record {record}")
                records.clear()  # Clear the records list after indexing

        # # Index remaining records if there are any
        if records:
            print(f"indexing remaining {len(records)} records")
            bulk(es, records)


if __name__ == "__main__":
    add_merged_works()
