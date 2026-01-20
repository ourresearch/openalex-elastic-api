from pathlib import Path

from elasticsearch_dsl import Q, Search, connections

from settings import ES_URL_WALDEN, WORKS_INDEX_LEGACY


def get_ids():
    s = Search(index=WORKS_INDEX_LEGACY)
    s = s.source(["id"])
    ids = []
    count = 0
    outfp = Path("work_ids_from_elasticsearch.txt")
    print(f"opening file for write: {outfp}")
    with outfp.open("w") as outf:
        for h in s.scan():
            outf.write(f"{h.id}\n")
            count += 1
            if (
                count in [100, 1000, 10000, 100000, 500000, 1000000, 5000000]
                or count % 10000000 == 0
            ):
                print(f"{count} ids written")
    print(f"done. {count} lines written")


if __name__ == "__main__":
    connections.create_connection(hosts=[ES_URL_WALDEN], timeout=600)
    get_ids()
