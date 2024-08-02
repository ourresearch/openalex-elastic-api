import json

from flask import request

from config.entity_config import entity_configs_dict
from config.property_config import property_configs_dict

OPENALEX_URL = "openalex.org"

id_mapping = {
    "w": "works",
    "a": "authors",
    "i": "institutions",
    "c": "concepts",
    "f": "funders",
    "p": "publishers",
    "s": "sources",
    "t": "topics",
}


def is_ui_format():
    format_param = request.args.get("format")
    return format_param == "ui"


def convert_openalex_id(old_id):
    if OPENALEX_URL in old_id:
        old_id = old_id.replace(f"https://{OPENALEX_URL}/", "")
        parts = old_id.split("/")
        if len(parts) == 1:
            # Internal IDs
            short_id = parts[-1]
            for letter, entity in id_mapping.items():
                if short_id.lower().startswith(letter):
                    return f"{entity}/{short_id}"
        elif len(parts) == 2:
            # External IDs
            return f"/{parts[-2]}/{parts[-1]}"
    return old_id


def format_as_ui(entity, data):
    results = []
    columns = entity_configs_dict[entity]["rowsToShowOnEntityPage"]
    print(f"columns to process: {columns}")
    data = json.loads(data)
    for column in columns:
        config = property_configs_dict[entity].get(column)
        is_list = column in property_configs_dict[entity] and property_configs_dict[
            entity
        ][column].get("isList")
        # unique columns
        if column == "grants.award_id":
            results.append(
                {
                    "value": [grant["award_id"] for grant in data["grants"]],
                    "config": config,
                }
            )
        elif column == "authorships.author.id":
            results.append(
                {
                    "value": [
                        {
                            "id": convert_openalex_id(authorship["author"]["id"]),
                            "display_name": authorship["author"]["display_name"],
                        }
                        for authorship in data["authorships"]
                    ],
                    "config": config,
                }
            )
        elif column == "authorships.institutions.id":
            results.append(
                {
                    "value": [
                        {
                            "id": convert_openalex_id(institution["id"]),
                            "display_name": institution["display_name"],
                        }
                        for authorship in data["authorships"]
                        for institution in authorship["institutions"]
                    ],
                    "config": config,
                }
            )
        elif column == "affiliations.institution.id":
            results.append(
                {
                    "value": [
                        {
                            "id": convert_openalex_id(affiliation["institution"]["id"]),
                            "display_name": affiliation["institution"]["display_name"],
                        }
                        for affiliation in data["affiliations"]
                    ],
                    "config": config,
                }
            )
        elif (
            column == "parent_institutions"
            or column == "child_institutions"
            or column == "related_institutions"
        ):
            relationship = column.split("_")[0]
            results.append(
                {
                    "value": [
                        {
                            "id": convert_openalex_id(institution["id"]),
                            "display_name": institution["display_name"],
                        }
                        for institution in data["associated_institutions"]
                        if institution["relationship"] == relationship
                    ],
                    "config": config,
                }
            )
        elif column == "publisher":
            results.append(
                {
                    "value": {
                        "id": convert_openalex_id(data["host_organization"])
                        if data.get("host_organization")
                        else None,
                        "display_name": data.get("host_organization_name"),
                    },
                    "config": config,
                }
            )
        elif column == "siblings":
            results.append(
                {
                    "value": [
                        {
                            "id": convert_openalex_id(sibling["id"]),
                            "display_name": sibling["display_name"],
                        }
                        for sibling in data["siblings"]
                    ],
                    "config": config,
                }
            )
        # normal columns
        elif "." not in column and not is_list:
            if column == "type" and entity == "works":
                value = f"/types/{data['type']}"
            elif column == "type" and entity == "sources":
                value = f"/source-types/{data['type']}"
            elif column == "id":
                value = convert_openalex_id(data["id"])
            else:
                value = data[column]

            if "id" in value and "display_name" in value:
                # override value since the result has id, display_name
                id_and_display_name = dict(value)
                value = {
                    "id": convert_openalex_id(id_and_display_name["id"]),
                    "display_name": id_and_display_name["display_name"],
                }
            results.append(
                {
                    "value": value,
                    "config": config,
                }
            )
        elif len(column.split(".")) == 2 and column.endswith(".id") and not is_list:
            first_key = column.split(".")[0]
            results.append(
                {
                    "value": {
                        "id": convert_openalex_id(data[first_key]["id"]),
                        "display_name": data[first_key]["display_name"],
                    },
                    "config": config,
                }
            )
        elif len(column.split(".")) == 3 and column.endswith(".id") and not is_list:
            first_key = column.split(".")[0]
            second_key = column.split(".")[1]
            results.append(
                {
                    "value": {
                        "id": convert_openalex_id(data[first_key][second_key]["id"])
                        if data.get(first_key)
                        else None,
                        "display_name": data[first_key][second_key]["display_name"],
                    },
                    "config": config,
                }
            )
        elif (len(column.split(".")) == 2) and not is_list:
            first_key = column.split(".")[0]
            second_key = column.split(".")[1]
            results.append(
                {
                    "value": data[first_key][second_key]
                    if first_key and data[first_key].get(second_key)
                    else None,
                    "config": config,
                }
            )
        elif column == "grants.funder":
            results.append(
                {
                    "value": [
                        {
                            "id": convert_openalex_id(grant["funder"]),
                            "display_name": grant["funder_display_name"],
                        }
                        for grant in data["grants"]
                    ],
                    "config": config,
                }
            )
        elif (len(column.split(".")) == 2) and is_list and column.split(".")[1] == "id":
            first_key = column.split(".")[0]
            results.append(
                {
                    "value": [
                        {
                            "id": convert_openalex_id(item["id"])
                            if item.get("id")
                            else None,
                            "display_name": item["display_name"],
                        }
                        for item in data[first_key]
                    ],
                    "config": config,
                }
            )

    # print columns that weren't processed
    columns_processed = [result["config"]["key"] for result in results]
    columns_not_processed = list(set(columns) - set(columns_processed))
    print(f"columns_not_processed: {columns_not_processed}")
    return results
