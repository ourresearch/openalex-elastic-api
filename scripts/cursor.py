import requests


def paginate():
    """Run cursor pagination."""
    r = requests.get(
        "http://127.0.0.1:5000/works?filter=is_paratext:false,from_publication_date:1980-04-01,to_publication_date:1980-04-30&per-page=200&sort=cited_by_count&cursor=*"
    )
    cursor = r.json()["meta"]["next_cursor"]
    count = r.json()["meta"]["count"]
    records = len(r.json()["results"])

    for i in range(1, 700):
        r = requests.get(
            f"http://127.0.0.1:5000/works?filter=is_paratext:false,from_publication_date:1980-04-01,to_publication_date:1980-04-30&sort=cited_by_count&per-page=200&cursor={cursor}"
        )
        cursor = r.json()["meta"]["next_cursor"]
        response_time = r.json()["meta"]["db_response_time_ms"]
        records = records + len(r.json()["results"])
        publication_date = r.json()["results"][0]["cited_by_count"]
        print(i, response_time, records, count, cursor, publication_date)


if __name__ == "__main__":
    paginate()
