from multiprocessing import Pool
from elasticsearch.helpers import bulk
from elasticsearch_dsl import Search, connections
from elasticsearch.exceptions import ConflictError
from settings import ES_URL_WALDEN, WORKS_INDEX_LEGACY

BATCH_SIZE = 100

def init_es():
    connections.create_connection(hosts=[ES_URL_WALDEN], timeout=30, alias='default')

def remove_duplicates(work_ids):

    actions = []
    count = 0

    for work_id in work_ids:
        count += 1
        actions.extend(find_id_and_prepare_delete(work_id))

        if len(actions) >= BATCH_SIZE:
            print(f"deleting batch, line count is {count}")
            bulk_delete(actions)
            actions = []

    if actions:
        bulk_delete(actions)


def find_id_and_prepare_delete(work_id):
    s = Search(index=WORKS_INDEX_LEGACY)
    formatted_id = f"https://openalex.org/{work_id}"

    s = s.filter("term", id=formatted_id).source(False)
    s = s.sort("-@timestamp")
    response = s.execute()

    actions = []
    if s.count() == 2:
        record = response.hits[1]
        actions.append({
            '_op_type': 'delete',
            '_index': record.meta.index,
            '_id': record.meta.id
        })

    return actions


def bulk_delete(actions):
    try:
        bulk(connections.get_connection(), actions)
        print(f"Bulk deleted {len(actions)} records.")
    except ConflictError as e:
        print(f"Conflict encountered during bulk delete: {e}")


def run_parallel():
    init_es()

    with open("duplicate_record_ids_works.csv", "r") as f:
        work_ids = [line.strip() for line in f]

    print(f"Total work IDs loaded: {len(work_ids)}")

    num_workers = 8
    chunk_size = len(work_ids) // num_workers

    with Pool(processes=num_workers, initializer=init_es) as pool:
        pool.map(remove_duplicates, [work_ids[i:i + chunk_size] for i in range(0, len(work_ids), chunk_size)])


if __name__ == "__main__":
    run_parallel()
