from core.group_by.utils import parse_group_by


def search_group_by_strings_with_q(params, result):
    result["meta"]["q"] = params["q"]
    if params["group_by"] and params["q"] and params["q"] != "''":
        result["group_by"] = search_group_by_results(
            params["group_by"], params["q"], result["group_by"], params["per_page"]
        )
        result["meta"]["count"] = len(result["group_by"])
    elif params["group_bys"] and params["q"] and params["q"] != "''":
        for group_by_item in params["group_bys"]:
            group_by_item, _ = parse_group_by(group_by_item)
            for group in result["group_bys"]:
                if group["group_by_key"] == group_by_item:
                    group["groups"] = search_group_by_results(
                        group_by_item,
                        params["q"],
                        group["groups"],
                        params["per_page"],
                    )
                    break
    return result


def search_group_by_results(group_by, q, result, per_page):
    filtered_result = []
    for i, r in enumerate(result):
        if len(filtered_result) == per_page:
            break
        if "author.id" in group_by:
            if all(x in str(r["key_display_name"]).lower() for x in q.lower().split()):
                filtered_result.append(r)
        else:
            if q.lower() in str(r["key_display_name"]).lower():
                filtered_result.append(r)
    return filtered_result
