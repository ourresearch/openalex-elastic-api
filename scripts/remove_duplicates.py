from elasticsearch.helpers import bulk
from elasticsearch_dsl import Search, connections
from elasticsearch.exceptions import ConflictError
from settings import ES_URL, WORKS_INDEX

BATCH_SIZE = 100  # Adjust the batch size based on your needs


def remove_duplicates():
    """Find and remove duplicates from works index."""
    actions = []
    count = 0

    with open("duplicate_record_ids_works.csv", "r") as f:
        for line in f:
            count += 1
            print(f"Processing line {count}")
            work_id = line.strip()
            actions.extend(find_id_and_prepare_delete(work_id))

            if len(actions) >= BATCH_SIZE:
                bulk_delete(actions)
                actions = []  # Reset actions after processing the batch

    # Process any remaining actions
    if actions:
        bulk_delete(actions)


def find_id_and_prepare_delete(work_id):
    """Find duplicates for a given work_id and prepare the delete actions."""
    s = Search(index=WORKS_INDEX)
    formatted_id = f"https://openalex.org/{work_id}"
    s = s.filter("term", id=formatted_id).source(False)
    s = s.sort("-@timestamp")
    response = s.execute()

    actions = []
    if s.count() == 2:
        record = response.hits[1]
        print(f"Adding duplicate record with id: {record.meta.id} in index: {record.meta.index}")
        actions.append({
            '_op_type': 'delete',
            '_index': record.meta.index,
            '_id': record.meta.id
        })

    return actions


def bulk_delete(actions):
    """Perform bulk deletion of the actions."""
    try:
        bulk(connections.get_connection(), actions)
        print(f"Bulk deleted {len(actions)} records.")
    except ConflictError as e:
        print(f"Conflict encountered during bulk delete: {e}")
    except Exception as e:
        print(f"Error during bulk delete: {e}")


if __name__ == "__main__":
    # Establish Elasticsearch connection
    connections.create_connection(hosts=[ES_URL], timeout=30)
    remove_duplicates()
