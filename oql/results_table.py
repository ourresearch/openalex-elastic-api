import requests

from config.entity_config import entity_configs_dict
from config.property_config import property_configs_dict


class ResultTable:
    def __init__(self, entity, columns, json_data):
        self.entity = entity
        self.columns = columns
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
        return [self.format_value(key, value) for key, value in row.items()]

    def format_value(self, key, value):
        column_type = self.get_column_type(key)
        if column_type == "entity":
            return {"type": column_type, "value": {
                "id": value,
                "display_name": self.ids_display_names()[value]
            }}
        elif column_type == "boolean":
            return {"type": column_type, "value": bool(value)}
        elif column_type == "number":
            return {"type": column_type, "value": int(value)}
        elif column_type == "entity_list":
            return {"type": "entity", "isList": True, "value": value}
        else:
            return {"type": column_type, "value": value}

    def ids_display_names(self):
        return {row['id']: row['display_name'] for row in self.json_data['results']}

    def get_column_type(self, column):
        return property_configs_dict[self.entity][column]["newType"]

    def response(self):
        return {
            "header": self.header(),
            "body": self.body()
        }


if __name__ == "__main__":
    entity = "works"
    columns = ["id", "display_name", "publication_year"]
    json_data = requests.get(f"https://api.openalex.org/works?select=id,display_name,publication_year").json()
    rt = ResultTable(entity, columns, json_data)
    print(rt.header())
    print(rt.body())
