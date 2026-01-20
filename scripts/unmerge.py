import csv
from elasticsearch_dsl import Search, connections
import settings


def unmerge():
    """Delete records from the merge-authors-v1 index in batches of 50."""
    with open("scripts/author_ids_to_fix.csv", "rt") as f:
        reader = csv.DictReader(f)
        total = 0
        batch = []

        for row in reader:
            total += 1
            formatted_id = f"https://openalex.org/A{row['merge_to_id']}"
            print(f"Deleting {formatted_id} ({total})")
            batch.append(formatted_id)

            if len(batch) >= 50:
                delete_batch(batch)
                batch = []

        if batch:
            delete_batch(batch)


def delete_batch(batch):
    """Delete a batch of records."""
    s = Search(index="merge-authors-v1").filter("terms", _id=batch)
    s.delete()


if __name__ == "__main__":
    connections.create_connection(hosts=[settings.ES_URL_WALDEN], timeout=30)
    unmerge()
