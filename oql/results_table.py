from combined_config import all_entities_config


class ResultTable:
    def __init__(self, entity, columns, json_data):
        self.entity = entity
        self.columns = (
            columns
            if columns
            else all_entities_config[entity]["columnsToShowOnTableRedshift"]
        )
        self.json_data = json_data
        self.config = all_entities_config[entity]

    def header(self):
        return [
            all_entities_config[self.entity]['properties'][column]
            for column in self.columns
            if column in all_entities_config[self.entity]['properties']
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
        return all_entities_config[self.entity]['properties'][column]["newType"]

    def is_list(self, column):
        return all_entities_config[self.entity]['properties'][column].get("isList", False)

    def is_external_id(self, column):
        return all_entities_config[self.entity]['properties'][column].get("isExternalId", False)

    def external_id_prefix(self, column):
        return all_entities_config[self.entity]['properties'][column].get("externalIdPrefix", "")

    def count(self):
        return len(self.json_data["results"])

    def convert_abtract_inverted_index(self, data):
        positions = [(key, ord) for key, values in data.items() for ord in values]
        sorted_positions = sorted(positions, key=lambda x: x[1])
        result = " ".join(key for key, _ in sorted_positions)
        return result

    def response(self):
        return {"results": {"header": self.header(), "body": self.body()}}
