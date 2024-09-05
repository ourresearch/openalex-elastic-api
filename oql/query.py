from sqlalchemy.engine.row import Row

from combined_config import all_entities_config
from oql.redshift import RedshiftQueryHandler

valid_entities = list(all_entities_config.keys())


class Query:
    """
    Query object to execute a query and return results. Also sets the defaults for the query.
    """
    def __init__(self, entity, filter_works, filter_aggs, show_columns, sort_by_column, sort_by_order):
        self.entity = entity or "works"
        self.filter_works = filter_works or []
        self.filter_aggs = filter_aggs or []
        self.sort_by_column = sort_by_column or self.default_sort_by_column()
        self.sort_by_order = sort_by_order or self.default_sort_by_order()
        self.show_columns = self.set_show_columns(show_columns)
        self.total_count = 0
        self.valid_columns = self.get_valid_columns()
        self.valid_sort_columns = self.get_valid_sort_columns()

    def get_filter_by(self):
        return []

    def execute(self):
        redshift_handler = RedshiftQueryHandler(
            entity=self.entity,
            filter_works=self.filter_works,
            filter_aggs=self.filter_aggs,
            sort_by_column=self.sort_by_column,
            sort_by_order=self.sort_by_order,
            show_columns=self.show_columns,
            valid_columns=self.valid_columns
        )
        total_count, results = redshift_handler.execute()
        self.total_count = total_count
        json_data = self.format_results_as_json(results)
        return json_data

    def format_results_as_json(self, results):
        json_data = {"results": []}
        columns = self.show_columns

        for r in results:
            model_instance = r[0] if isinstance(r, Row) else r

            if model_instance.id == "works/W4285719527":
                # deleted work, skip
                continue

            result_data = {}
            for column in columns:
                # use the redshift display column from config
                redshift_column = all_entities_config[self.entity]['columns'][column]["redshiftDisplayColumn"]

                if hasattr(model_instance, redshift_column):
                    value = getattr(model_instance, redshift_column)

                    # if the value is callable (i.e., it's a property method), call it
                    if callable(value):
                        value = value()
                else:
                    # otherwise, look for the value in the result set
                    value = r[redshift_column] if redshift_column in r.keys() else None

                result_data[column] = value

            result_data["id"] = model_instance.id
            json_data["results"].append(result_data)

        return json_data

    def get_valid_columns(self):
        return (
            all_entities_config[self.entity]['columns'].keys()
            if self.entity and self.entity in all_entities_config
            else []
        )

    def set_show_columns(self, show_columns=None):
        if show_columns:
            # if show_columns is passed in, use that
            columns = show_columns
        elif self.entity and self.entity in all_entities_config:
            # otherwise, use the default columns for the entity
            columns = all_entities_config[self.entity]["showOnTablePage"]
        else:
            # if the entity is not valid, return an empty list
            columns = []

        # add the sort column if it's not already in the list
        if self.sort_by_column and self.sort_by_column not in columns:
            columns.append(self.sort_by_column)
        return columns

    def default_sort_by_column(self):
        entities_with_works_count = ["authors", "countries", "institutions", "keywords", "sources", "topics"]
        if self.entity == "works":
            return "cited_by_count"
        elif self.entity == "summary":
            return None
        elif self.entity in entities_with_works_count:
            return "count(works)"
        else:
            return "display_name"

    @staticmethod
    def default_sort_by_order():
        return "desc"

    def get_valid_sort_columns(self):
        if not self.entity or self.entity and self.entity not in all_entities_config:
            return []
        return [
            key
            for key, values in all_entities_config[self.entity]['columns'].items()
            if "sort" in values.get("actions", [])
        ]

    def property_type(self, column):
        for property_config in all_entities_config.get(self.entity, {}).get('columns').values():
            if property_config.get("id", "") == column:
                return property_config.get("type", "string")

    def to_dict(self):
        return {
            "get_rows": self.entity,
            "filter_works": self.filter_works,
            "filter_aggs": self.filter_aggs,
            "show_columns": self.show_columns,
            "sort_by_column": self.sort_by_column,
            "sort_by_order": self.sort_by_order,
        }



def convert_to_snake_case(name):
    return name.strip().replace(" ", "_").lower()
