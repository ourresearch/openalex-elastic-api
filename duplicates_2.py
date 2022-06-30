import requests
from elasticsearch_dsl import A, Search, connections

from settings import ES_URL, WORKS_INDEX


def paginate():
    r = requests.get(
        "http://127.0.0.1:5000/works?filter=publication_year:2020&per-page=200&cursor=*"
    )
    cursor = r.json()["meta"]["next_cursor"]
    count = len(r.json()["results"])
    duplicate_count = 0

    while cursor:
        duplicates = []
        r = requests.get(
            f"http://127.0.0.1:5000/works?filter=publication_year:2020&per-page=200&cursor={cursor}"
        )
        cursor = r.json()["meta"]["next_cursor"]
        records = r.json()["results"]
        count = count + len(r.json()["results"])
        print(f"records processed: {count}")
        for r in records:
            s = Search(index=WORKS_INDEX)
            s = s.filter("term", id=r["id"])
            s = s.sort("-@timestamp")
            response = s.execute()
            if s.count() == 2:
                record = response.hits[0]
                duplicates.append(record.id)
        duplicate_count = duplicate_count + len(duplicates)
        print(f"duplicate count: {duplicate_count}")


if __name__ == "__main__":
    connections.create_connection(hosts=[ES_URL], timeout=30)
    paginate()
