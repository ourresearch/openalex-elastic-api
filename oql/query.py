from sqlalchemy.engine.row import Row

from combined_config import all_entities_config
from oql.elastic import ElasticQueryHandler
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
        self.source = None

        self.elastic_handler = ElasticQueryHandler(
            entity=self.entity,
            filter_works=self.filter_works,
            filter_aggs=self.filter_aggs,
            sort_by_column=self.sort_by_column,
            sort_by_order=self.sort_by_order,
            show_columns=self.show_columns,
            valid_columns=self.valid_columns
        )
        self.redshift_handler = RedshiftQueryHandler(
            entity=self.entity,
            filter_works=self.filter_works,
            filter_aggs=self.filter_aggs,
            sort_by_column=self.sort_by_column,
            sort_by_order=self.sort_by_order,
            show_columns=self.show_columns,
            valid_columns=self.valid_columns
        )

    def get_filter_by(self):
        return []

    def execute(self):
        if self.entity == "summary":
            results = self.redshift_handler.execute_summary()
            self.total_count = results["count"]
            json_data = {"results": [results]}
        
        elif self.elastic_handler.is_valid():
            print(f"Initiating elastic query for {self.entity}")
            total_count, results = self.elastic_handler.execute()
            self.total_count = total_count
            json_data = self.format_elastic_results_as_json(results)
            self.source = "elastic"
        
        else:
            print(f"Initiating redshift query for {self.entity}")
            total_count, results = self.redshift_handler.execute()
            self.total_count = total_count
            json_data = self.format_redshift_results_as_json(results)
            self.source = "redshift"
        
        return json_data

    def format_redshift_results_as_json(self, results):
        """
        Convert row-based results (no full ORM object) into the old JSON structure,
        but skip property/callable logic.
        """
        json_data = {"results": []}
        columns = list(set(self.show_columns + ["id"]))

        print("format_redshift_results_as_json, first row:")
        if results:
            print(results[0])
            print(type(results[0]))
            print(results[0].keys() if hasattr(results[0], "keys") else "No keys")
        print("***")
        print("processing rows")

        for row in results:
            if "id" in row and row["id"] == "works/W4285719527":
                continue # Deleted Work ID

            result_data = {}
            #result_data["id"] = row.get("id")

            for column in columns:
                # Use config to get the underlying redshift column name
                column_info = all_entities_config[self.entity]["columns"].get(column, {})
                redshift_column = column_info.get("redshiftDisplayColumn", None)

                # 1) If the row has a direct aggregator label or same-named key, use that
                if column in row.keys():
                    value = row[column]
                # 2) Otherwise, if we have a known DB column name in row, use that
                elif redshift_column and redshift_column in row.keys():
                    value = row[redshift_column]
                else:
                    # Not found in row
                    value = None

                result_data[column] = value

            json_data["results"].append(result_data)
        print("finished processing rows", flush=True)
        return json_data

    def Xformat_redshift_results_as_json(self, results):
        json_data = {"results": []}
        columns = self.show_columns

        print("format_redshift_results_as_json")
        for r in results:
            # print(r)
            model_instance = r[0] if isinstance(r, Row) else r

            # print(model_instance, flush=True)
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

    def format_elastic_results_as_json(self, results):
        json_data = {"results": []}
        columns = self.show_columns

        for r in results:
            result_data = {}
            for column in columns:
                if column in r.keys():
                    value = r[column]
                else:
                    value = None
                result_data[column] = value

            result_data["id"] = r["id"]
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
            if "display_name" not in columns and self.entity != "summary":
                columns.insert(0, "display_name")
        elif self.entity == "summary":
            return ["count", "sum(cited_by_count)", "mean(cited_by_count)",  "mean(fwci)", "sum(is_oa)", "percent(is_oa)"]
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
        if self.entity == "works":
            return "cited_by_count"
        elif self.entity == "summary":
            return None
        else:
            return "count(works)"

    @staticmethod
    def default_sort_by_order():
        return "desc"

    def get_valid_sort_columns(self):
        if not self.entity or self.entity and self.entity not in all_entities_config:
            return []
        return [
            key
            for key, values in all_entities_config[self.entity]['columns'].items()
            if "sort" in (values.get("actions") or [])
        ]

    def property_type(self, column):
        for property_config in all_entities_config.get(self.entity, {}).get('columns').values():
            if property_config.get("id", "") == column:
                return property_config.get("type", "string")

    def get_sql(self):
        return self.redshift_handler.get_sql()

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
