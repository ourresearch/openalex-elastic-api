import json

import requests


def build_tree():
    result = {}
    # level 0
    r = requests.get("https://api.openalex.org/concepts?filter=level:0")
    for row in r.json()["results"]:
        new_key = f"{row['id']} ({row['display_name']})"
        result[new_key] = {}

    # level 1
    for page in range(1, 3):
        r = requests.get(
            f"https://api.openalex.org/concepts?filter=level:1&per-page=200&page={page}"
        )
        for row in r.json()["results"]:
            for ancestor in row["ancestors"]:
                if ancestor["level"] == 0:
                    ancestor_key = f"{ancestor['id']} ({ancestor['display_name']})"
                    new_key = f"{row['id']} ({row['display_name']})"
                    result[ancestor_key][new_key] = {}

    # level 2
    for page in range(1, 120):
        print(f"page (level 2): {page}")
        if page == 1:
            cursor = "*"
        else:
            cursor = r.json()["meta"]["next_cursor"]
        if cursor == None:
            break
        r = requests.get(
            f"https://api.openalex.org/concepts?filter=level:2&per-page=200&cursor={cursor}&mailto=team@ourresearch.org"
        )
        for key, level_1 in result.items():
            for row in r.json()["results"]:
                for ancestor in row["ancestors"]:
                    ancestor_key = f"{ancestor['id']} ({ancestor['display_name']})"
                    new_key = f"{row['id']} ({row['display_name']})"
                    if (
                        ancestor["level"] == 1
                        and type(level_1.get(ancestor_key)) == dict
                    ):
                        result[key][ancestor_key][new_key] = {}

    # level 3
    level_3_results = []
    for page in range(1, 140):
        print(f"page (level 3): {page}")
        if page == 1:
            cursor = "*"
        else:
            cursor = r.json()["meta"]["next_cursor"]
        if cursor == None:
            break
        r = requests.get(
            f"https://api.openalex.org/concepts?filter=level:3&per-page=200&cursor={cursor}&mailto=team@ourresearch.org"
        )
        for item in r.json()["results"]:
            level_3_results.append(item)

    print("assigning level 3")
    for level_1_key, level_1 in result.items():
        for level_2_key, level_2 in level_1.items():
            for row in level_3_results:
                for ancestor in row["ancestors"]:
                    ancestor_key = f"{ancestor['id']} ({ancestor['display_name']})"
                    new_key = f"{row['id']} ({row['display_name']})"
                    if (
                        ancestor["level"] == 2
                        and type(level_2.get(ancestor_key)) == dict
                    ):
                        result[level_1_key][level_2_key][ancestor_key][new_key] = {}
    print("done assigning level 3")

    # level 4
    level_4_results = []
    for page in range(1, 120):
        print(f"page (level 4): {page}")
        if page == 1:
            cursor = "*"
        else:
            cursor = r.json()["meta"]["next_cursor"]
        if cursor == None:
            break
        r = requests.get(
            f"https://api.openalex.org/concepts?filter=level:4&per-page=200&cursor={cursor}&mailto=team@ourresearch.org"
        )
        for item in r.json()["results"]:
            level_4_results.append(item)

    print("assigning level 4")
    for level_1_key, level_1 in result.items():
        for level_2_key, level_2 in level_1.items():
            for level_3_key, level_3 in level_2.items():
                for row in level_4_results:
                    for ancestor in row["ancestors"]:
                        ancestor_key = f"{ancestor['id']} ({ancestor['display_name']})"
                        new_key = f"{row['id']} ({row['display_name']})"
                        if (
                            ancestor["level"] == 3
                            and type(level_3.get(ancestor_key)) == dict
                        ):
                            result[level_1_key][level_2_key][level_3_key][ancestor_key][
                                new_key
                            ] = {}
    print("done assigning level 4")

    # level 5
    level_5_results = []
    for page in range(1, 120):
        print(f"page (level 5): {page}")
        if page == 1:
            cursor = "*"
        else:
            cursor = r.json()["meta"]["next_cursor"]
        if cursor == None:
            break
        r = requests.get(
            f"https://api.openalex.org/concepts?filter=level:5&per-page=200&cursor={cursor}&mailto=team@ourresearch.org"
        )
        for item in r.json()["results"]:
            level_5_results.append(item)

    print("assigning level 5")
    for level_1_key, level_1 in result.items():
        for level_2_key, level_2 in level_1.items():
            for level_3_key, level_3 in level_2.items():
                for level_4_key, level_4 in level_3.items():
                    for row in r.json()["results"]:
                        for ancestor in row["ancestors"]:
                            ancestor_key = (
                                f"{ancestor['id']} ({ancestor['display_name']})"
                            )
                            new_key = f"{row['id']} ({row['display_name']})"
                            if (
                                ancestor["level"] == 4
                                and type(level_4.get(ancestor_key)) == dict
                            ):
                                result[level_1_key][level_2_key][level_3_key][
                                    level_4_key
                                ][ancestor_key][new_key] = {}
    print("done assigning level 5")
    return result


if __name__ == "__main__":
    tree = build_tree()
    with open("concepts_tree.json", "w") as fp:
        json.dump(tree, fp, indent=4)
