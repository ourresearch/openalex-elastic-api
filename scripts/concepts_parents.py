import csv

import requests


def get_parents(row):
    parent_ids = []
    parent_names = []
    url = row["openalex_id"].replace(
        "https://openalex.org/", "https://api.openalex.org/concepts/"
    )
    url = url + "?mailto=team@ourresearch.org"
    r = requests.get(url)
    level = int(r.json()["level"])
    ancestors = r.json()["ancestors"]
    if level == 0:
        return None
    else:
        relevant_level = level - 1
        for ancestor in ancestors:
            if int(ancestor["level"]) == relevant_level:
                parent_ids.append(ancestor["id"])
                parent_names.append(ancestor["display_name"])
        return ", ".join(parent_ids), ", ".join(parent_names)


if __name__ == "__main__":
    results = []
    with open("concepts.csv") as csvfile:
        reader = csv.DictReader(csvfile)
        for i, row in enumerate(reader):
            print(i)
            parents = get_parents(row)
            row["parent_ids"] = parents[0] if parents else None
            row["parent_display_names"] = parents[1] if parents else None
            results.append(row)
    with open("concepts_parents.csv", "w") as output_file:
        dict_writer = csv.DictWriter(output_file, results[0].keys())
        dict_writer.writeheader()
        dict_writer.writerows(results)
