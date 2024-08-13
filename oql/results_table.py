from config.entity_config import entity_configs_dict
from config.property_config import property_configs_dict
from config.stats_config import stats_configs_dict
from ids.ui_format import convert_openalex_id


class ResultTable:
    def __init__(self, entity, columns, json_data):
        self.entity = entity
        self.columns = (
            columns
            if columns
            else entity_configs_dict[entity]["rowsToShowOnTablePage"]
        )
        self.json_data = json_data
        self.config = entity_configs_dict[entity]

    def header(self):
        return [
            property_configs_dict[self.entity][column]
            for column in self.columns
            if self.entity in property_configs_dict
            and column in property_configs_dict[self.entity]
        ]

    def body(self):
        return [self.format_row(row) for row in self.json_data["results"]]

    def format_row(self, row):
        row_id = row.get("id")
        result = {"id": convert_openalex_id(row_id), "cells": []}
        for column in self.columns:
            value = self.get_column_value(row, column)
            # if value is a list of dictionaries, remove the duplicates
            if isinstance(value, list) and value and isinstance(value[0], dict):
                value = [
                    dict(t)
                    for t in {tuple(d.items()) for d in value if type(d) is dict}
                ]
            result["cells"].append(self.format_value(column, value))
        return result

    def get_column_value(self, row, column):
        if column == "grants.funder":
            return self.get_funder_with_display_name(row, column)
        if column == "host_organization" and self.entity == "sources":
            return self.get_host_organization(row)
        elif column in [
            "child_institutions",
            "parent_institutions",
            "related_institutions",
        ]:
            return self.get_related_institutions_with_display_name(row, column)
        elif self.is_list(column) and "." in column:
            return self.get_nested_values(row, column)
        elif self.is_list(column):
            return self.get_values(row, column)
        elif self.is_external_id(column):
            value = self.get_nested_value(row, column)
            prefix = self.external_id_prefix(column)
            formatted_id = f"{prefix}/{value}"
            return (
                {
                    "id": formatted_id,
                    "display_name": value,
                }
                if formatted_id and value
                else None
            )
        elif column.endswith(".id") and not self.is_list(column):
            return self.get_entity_with_display_name(row, column)
        return self.get_nested_value(row, column)

    def get_entity_with_display_name(self, data, path):
        base_path = path.rsplit(".", 1)[0]
        id_value = self.get_nested_value(data, path)
        display_name = self.get_nested_value(data, f"{base_path}.display_name")
        return {"id": convert_openalex_id(id_value), "display_name": display_name}

    def get_funder_with_display_name(self, row, column):
        funder_id = self.get_nested_value(row, column)
        funder_display_name = self.get_nested_value(row, "grants.funder_display_name")
        return (
            {
                "id": convert_openalex_id(funder_id),
                "display_name": funder_display_name,
            }
            if funder_id and funder_display_name
            else None
        )

    def get_host_organization(self, row):
        host_organization_id = row.get("host_organization")
        host_organization_display_name = row.get("host_organization_name")
        return (
            {
                "id": convert_openalex_id(host_organization_id),
                "display_name": host_organization_display_name,
            }
            if host_organization_id and host_organization_display_name
            else None
        )

    def get_related_institutions_with_display_name(self, row, column):
        relationship = column.split("_")[0]
        institutions = row.get("associated_institutions", [])
        return [
            {
                "id": convert_openalex_id(institution["id"]),
                "display_name": institution["display_name"],
            }
            for institution in institutions
            if institution["relationship"] == relationship
        ]

    def get_nested_value(self, data, path):
        keys = path.split(".") if path else []
        for key in keys:
            if isinstance(data, dict):
                data = data.get(key)
                if path == "grants.funder":
                    print(data)
            else:
                return None
        if "abstract_inverted_index" in keys and data:
            data = self.convert_abtract_inverted_index(data)
        return convert_openalex_id(data)

    def get_values(self, data, path):
        return [convert_openalex_id(value) for value in data.get(path, [])]

    def get_nested_values(self, data, path):
        keys = path.split(".")
        list_key = keys[0]
        list_of_dicts = data.get(list_key, [])
        remaining_keys = keys[1:]
        values = []
        for dict_ in list_of_dicts:
            if remaining_keys:
                nested_key = remaining_keys[0]
                if isinstance(dict_.get(nested_key), list):
                    nested_values = self.get_nested_values(
                        dict_, ".".join(remaining_keys)
                    )
                    values.extend(nested_values)
                else:
                    if remaining_keys[-1] == "id":
                        modified_keys = remaining_keys[:-1] + ["display_name"]
                        value = self.get_nested_value(dict_, ".".join(remaining_keys))
                        display_name = self.get_nested_value(
                            dict_, ".".join(modified_keys)
                        )
                        values.append(
                            {
                                "id": convert_openalex_id(value),
                                "display_name": display_name,
                            }
                        )
                    else:
                        value = self.get_nested_value(dict_, ".".join(remaining_keys))
                        values.append(value)
            else:
                values.append(dict_)
        return values

    def format_value(self, key, value):
        column_type = self.get_column_type(key)
        if column_type == "boolean":
            return {"type": column_type, "value": bool(value)}
        elif column_type == "number":
            return {"type": column_type, "value": value}
        elif column_type == "entity_list":
            return {"type": "entity", "isList": True, "value": value}
        else:
            return {"type": column_type, "value": value}

    def get_column_type(self, column):
        return property_configs_dict[self.entity][column]["newType"]

    def is_list(self, column):
        return property_configs_dict[self.entity][column].get("isList", False)

    def is_external_id(self, column):
        return property_configs_dict[self.entity][column].get("isExternalId", False)

    def external_id_prefix(self, column):
        return property_configs_dict[self.entity][column].get("externalIdPrefix", "")

    def count(self):
        return self.json_data["meta"]["count"]

    def convert_abtract_inverted_index(self, data):
        positions = [(key, ord) for key, values in data.items() for ord in values]
        sorted_positions = sorted(positions, key=lambda x: x[1])
        result = " ".join(key for key, _ in sorted_positions)
        return result

    def response(self):
        return {"results": {"header": self.header(), "body": self.body()}}


class ResultTableRedshift:
    def __init__(self, entity, columns, json_data):
        self.entity = entity
        self.columns = (
            columns
            if columns
            else entity_configs_dict[entity]["columnsToShowOnTableRedshift"]
        )
        self.json_data = json_data
        self.config = entity_configs_dict[entity]

    def header(self):
        return [
            property_configs_dict[self.entity][column]
            for column in self.columns
            if self.entity in property_configs_dict
               and column in property_configs_dict[self.entity]
        ]

    def body(self):
        return [self.format_row(row) for row in self.json_data["results"]]

    def format_row(self, row):
        row_id = row.get("id")
        result = {"id": row_id, "cells": []}
        for column in self.columns:
            # get the value of the column
            value = row.get(column)
            result["cells"].append(self.format_value(column, value))
        return result

    def format_value(self, key, value):
        column_type = self.get_column_type(key)
        if column_type == "boolean":
            return {"type": column_type, "value": bool(value)}
        elif column_type == "number":
            return {"type": column_type, "value": value}
        elif column_type == "entity_list":
            return {"type": "entity", "isList": True, "value": value}
        else:
            return {"type": column_type, "value": value}

    def get_column_type(self, column):
        return property_configs_dict[self.entity][column]["newType"]

    def is_list(self, column):
        return property_configs_dict[self.entity][column].get("isList", False)

    def is_external_id(self, column):
        return property_configs_dict[self.entity][column].get("isExternalId", False)

    def external_id_prefix(self, column):
        return property_configs_dict[self.entity][column].get("externalIdPrefix", "")

    def count(self):
        return len(self.json_data["results"])

    def convert_abtract_inverted_index(self, data):
        positions = [(key, ord) for key, values in data.items() for ord in values]
        sorted_positions = sorted(positions, key=lambda x: x[1])
        result = " ".join(key for key, _ in sorted_positions)
        return result

    def response(self):
        return {"results": {"header": self.header(), "body": self.body()}}
