import requests


# initial run

r = requests.get("http://127.0.0.1:5000/works?cursor=*&per-page=200&select=id")
count = 0
if r.status_code == 200:
    for record in r.json()["results"]:
        with open("license.csv", "a") as f:
            f.write(f"{record['id']}\n")
        count += 1


cursor = r.json()["meta"]["next_cursor"] if "next_cursor" in r.json()["meta"] else None

# loop through all pages
while cursor:
    r = requests.get(
        f"http://127.0.0.1:5000/works?cursor={cursor}&per-page=200&select=id"
    )
    if r.status_code == 200:
        for record in r.json()["results"]:
            with open("license.csv", "a") as f:
                f.write(f"{record['id']}\n")
            count += 1

        cursor = (
            r.json()["meta"]["next_cursor"]
            if "next_cursor" in r.json()["meta"]
            else None
        )
        print(f"Processed {count} records")
