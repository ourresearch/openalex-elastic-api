import csv

from elasticsearch_dsl import Q, Search, connections

from settings import ES_URL, WORKS_INDEX


def get_ids():
    s = Search(index=WORKS_INDEX)
    s = s.extra(size=10)
    default_sort = ["-publication_date", "id"]
    s = s.sort(*default_sort)
    s = s.source(["id", "publication_date"])
    response = s.execute()
    ids = []
    count = 0
    for r in response:
        count = count + 1
        ids.append(r.id)
        search_after = [r.publication_date, r.id]
        print(count)
    with open("ids.csv", "w+") as f:
        write = csv.writer(f, quoting=csv.QUOTE_ALL, delimiter="\n")
        write.writerows([ids])

    while True:
        s = Search(index=WORKS_INDEX)
        s = s.extra(size=10)
        default_sort = ["-publication_date", "id"]
        s = s.extra(search_after=search_after)
        s = s.source(["id", "publication_date"])
        s = s.sort(*default_sort)
        response = s.execute()
        ids = []
        for r in response:
            count = count + 1
            ids.append(r.id)
            print(count)
        if not ids:
            break
        search_after = [r.publication_date, r.id]
        with open("ids.csv", "a") as f:
            write = csv.writer(f, quoting=csv.QUOTE_ALL, delimiter="\n")
            write.writerows([ids])
        print(search_after)


if __name__ == "__main__":
    connections.create_connection(hosts=[ES_URL], timeout=30)
    get_ids()
