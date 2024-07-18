import requests

from config.entity_config import entity_configs_dict
from config.property_config import property_configs_dict


class ResultTable:
    def __init__(self, entity, columns, json_data):
        self.entity = entity
        self.columns = columns if columns else entity_configs_dict[entity]['rowsToShowOnEntityPage']
        self.json_data = json_data
        self.config = entity_configs_dict[entity]

    def header(self):
        return [
            property_configs_dict[self.entity][column]
            for column in self.columns
            if self.entity in property_configs_dict and column in property_configs_dict[self.entity]
        ]

    def body(self):
        return [self.format_row(row) for row in self.json_data['results']]

    def format_row(self, row):
        result = []
        for column in self.columns:
            value = self.get_column_value(row, column)
            result.append(self.format_value(column, value))
        return result

    def get_column_value(self, row, column):
        if column == "abstract" and "abstract_inverted_index" in row:
            return row["abstract_inverted_index"]

        if self.is_list(column):
            return self.get_nested_values(row, column)

        if column.endswith(".id") and not self.is_list(column):
            return self.get_entity_with_display_name(row, column)

        return self.get_nested_value(row, column)

    def get_entity_with_display_name(self, data, path):
        base_path = path.rsplit(".", 1)[0]
        id_value = self.get_nested_value(data, path)
        display_name = self.get_nested_value(data, f"{base_path}.display_name")
        return {"id": id_value, "display_name": display_name}

    @staticmethod
    def get_nested_value(data, path):
        keys = path.split(".") if path else []
        for key in keys:
            if isinstance(data, dict):
                data = data.get(key)
            else:
                return None
        return data

    def get_nested_values(self, data, path):
        list_key = path.split(".")[0]
        list_of_dicts = data.get(list_key, [])
        keys = path.split(".")[1:]
        values = []
        for dict_ in list_of_dicts:
            if keys and keys[-1] == "id":
                modified_keys = keys[:-1] + ["display_name"]
                value = self.get_nested_value(dict_, ".".join(keys))
                display_name = self.get_nested_value(dict_, ".".join(modified_keys))
                values.append({"id": value, "display_name": display_name})
            else:
                value = self.get_nested_value(dict_, ".".join(keys))
                values.append(value)
        return values

    def format_value(self, key, value):
        column_type = self.get_column_type(key)
        if column_type == "entity" and key == "id":
            return {"type": column_type, "value": {
                "id": value,
                "display_name": self.ids_display_names()[value]
            }}
        elif column_type == "boolean":
            return {"type": column_type, "value": bool(value)}
        elif column_type == "number":
            return {"type": column_type, "value": value}
        elif column_type == "entity_list":
            return {"type": "entity", "isList": True, "value": value}
        else:
            return {"type": column_type, "value": value}

    def ids_display_names(self):
        return {row['id']: row['display_name'] for row in self.json_data['results']}

    def get_column_type(self, column):
        return property_configs_dict[self.entity][column]["newType"]

    def is_list(self, column):
        return property_configs_dict[self.entity][column].get("isList", False)

    def response(self):
        return {
            "header": self.header(),
            "body": self.body()
        }


if __name__ == "__main__":
    entity = "works"
    columns = []
    json_data = requests.get(f"https://api.openalex.org/works").json()
    rt = ResultTable(entity, columns, json_data)
    rt.header()
    rt.body()
