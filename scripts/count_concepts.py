import csv
import json


def get_all_keys(d):
    for key, value in d.items():
        yield key
        if isinstance(value, dict):
            yield from get_all_keys(value)


if __name__ == "__main__":
    with open("concepts_tree.json") as jsonfile:
        data = json.load(jsonfile)

    results = []
    # level 0 keys
    for key1, val1 in data.items():
        keys = get_all_keys(data[key1])
        keys_list = [key for key in keys]
        results.append({"openalex_id": key1, "child_count": len(keys_list)})
        # print(key1, len(keys_list))

        # level 1
        for key2, val2 in val1.items():
            keys = get_all_keys(data[key1][key2])
            keys_list = [key for key in keys]
            results.append({"openalex_id": key2, "child_count": len(keys_list)})
            # print(key2, len(keys_list))

            # level 2
            for key3, val3 in val2.items():
                keys = get_all_keys(data[key1][key2][key3])
                keys_list = [key for key in keys]
                results.append({"openalex_id": key3, "child_count": len(keys_list)})
                # print(key3, len(keys_list))

                # level 3
                for key4, val4 in val3.items():
                    keys = get_all_keys(data[key1][key2][key3][key4])
                    keys_list = [key for key in keys]
                    results.append({"openalex_id": key4, "child_count": len(keys_list)})
                    # print(key4, len(keys_list))

                    # level 4
                    for key5, val5 in val4.items():
                        keys = get_all_keys(data[key1][key2][key3][key4][key5])
                        keys_list = [key for key in keys]
                        results.append(
                            {"openalex_id": key5, "child_count": len(keys_list)}
                        )
                        # print(key5, len(keys_list)
    print(len(results))
    keys = results[0].keys()
    with open("concept_count.csv", "w") as output_file:
        dict_writer = csv.DictWriter(output_file, keys)
        dict_writer.writeheader()
        dict_writer.writerows(results)
