from combined_config import all_entities_config


class ResultTable:
    def __init__(self, entity, show_columns, json_data, page=1, per_page=100, total_count=0):
        self.entity = entity
        self.show_columns = show_columns
        self.json_data = json_data
        self.page = page
        self.per_page = per_page
        self.total_count = total_count

    def header(self):
        return [
            all_entities_config[self.entity]['columns'][column]
            for column in self.show_columns
            if column in all_entities_config[self.entity]['columns']
        ]

    def body(self):
        return [self.format_row(row) for row in self.json_data["results"]]

    def format_row(self, row):
        row_id = row.get("id")
        result = {"id": row_id, "cells": []}
        for column in self.show_columns:
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
        return all_entities_config[self.entity]['columns'][column]["type"]

    def is_list(self, column):
        return all_entities_config[self.entity]['columns'][column].get("isList", False)

    def is_external_id(self, column):
        return all_entities_config[self.entity]['columns'][column].get("isExternalId", False)

    def external_id_prefix(self, column):
        return all_entities_config[self.entity]['columns'][column].get("externalIdPrefix", "")

    def count(self):
        return len(self.json_data["results"])

    def convert_abtract_inverted_index(self, data):
        positions = [(key, ord) for key, values in data.items() for ord in values]
        sorted_positions = sorted(positions, key=lambda x: x[1])
        result = " ".join(key for key, _ in sorted_positions)
        return result

    def meta(self):
        return {
            "count": self.total_count,
            "page": self.page,
            "per_page": self.per_page,
            "oql": None,
            "v1": None,
        }

    def response(self):
        # Build the full response, including metadata and results
        return {
            "meta": self.meta(),
            "results_header": self.header(),
            "results": self.body(),
        }
