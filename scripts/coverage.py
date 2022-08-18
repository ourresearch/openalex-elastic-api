import csv

import requests

if __name__ == "__main__":
    results = []
    for year in range(2000, 2023):
        r = requests.get(
            f"https://api.openalex.org/works?filter=has_fulltext:true,publication_year:{year}"
        )
        has_fulltext_count = r.json()["meta"]["count"]

        r = requests.get(
            f"https://api.openalex.org/works?filter=publication_year:{year}"
        )
        year_count = r.json()["meta"]["count"]
        results.append(
            {
                "year": year,
                "fulltext_count": has_fulltext_count,
                "year_count": year_count,
            }
        )
    print(results)
    keys = results[0].keys()
    with open("abstracts.csv", "w", newline="") as output_file:
        dict_writer = csv.DictWriter(output_file, keys)
        dict_writer.writeheader()
        dict_writer.writerows(results)
