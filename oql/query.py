from datetime import datetime, timezone

from sqlalchemy.engine.row import Row

from combined_config import all_entities_config
from oql.elastic import ElasticQueryHandler
from oql.redshift import RedshiftQueryHandler
from oql.models import get_entity_class, is_model_property, is_model_hybrid_property


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
        timestamps = {"started": datetime.now(timezone.utc).isoformat()}
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
            timestamps["core_query_completed"] = datetime.now(timezone.utc).isoformat()
            json_data = self.format_redshift_results_as_json(results)
            timestamps["secondary_queries_completed"] = datetime.now(timezone.utc).isoformat()
            self.source = "redshift"

        timestamps["completed"] = datetime.now(timezone.utc).isoformat()
        json_data["timestamps"] = timestamps

        return json_data

    def format_redshift_results_as_json(self, results):
        """
        Convert row-based results (no full ORM object) into the old JSON structure,
        but skip property/callable logic.
        """
        json_data = {"results": []}

        output_columns = list(set(self.show_columns + ["id"]))
        entity_class = get_entity_class(self.entity)
        entity_columns_config = all_entities_config[self.entity]["columns"]
        #print(f"output_columns: {output_columns}", flush=True)
        redshift_columns = {column: entity_columns_config.get(column, {}).get("redshiftDisplayColumn", None) for column in output_columns}

        #print(f"redshift_display_columns: {redshift_display_columns}", flush=True)

        for row in results:
            # Create an ephemeral model instance so we can call property methods
            ephemeral_model = entity_class()
           # print(f"Row has keys: {row.keys()}", flush=True)
            
            # Populate ephemeral model from the row
            for key in row.keys():
                redshift_column = redshift_columns.get(key)
                #print(f"key / redshift_display_column: {key} / {redshift_display_column}", flush=True)
                if redshift_column is None:
                    print(f"missing redshift column for key: {key}", flush=True)
                    continue
                if hasattr(entity_class, redshift_column) and not is_model_hybrid_property(redshift_column, entity_class):
                    #print(f"Ephemeral Model: Setting column: {key} to {row[key]}", flush=True)
                    setattr(ephemeral_model, redshift_column, row[key])

            # Skip "deleted" works
            if ephemeral_model.id == "works/W4285719527":
                continue

            result_data = {}

            # Build final row data
            for col_name in output_columns:
                redshift_column = redshift_columns.get(col_name)
                # print(f"Looking at {col_name} / {redshift_display_column}", flush=True)
                if col_name not in row.keys():
                    pass
                    #print(f"Column {col_name} not found in row")
                else:
                    pass
                    #print(f"with row value: {row[col_name]}", flush=True)
                # If ephemeral_model property
                if is_model_property(redshift_column, entity_class):
                    attr_value = getattr(ephemeral_model, redshift_column, None)
                    if callable(attr_value):
                        #print("Calling property method", flush=True)
                        attr_value = attr_value()
                    result_data[col_name] = attr_value
                    #print(f"Setting column: {col_name} to {attr_value}", flush=True)
                    continue

                if col_name in row.keys():
                    result_data[col_name] = row[col_name]
                    #print(f"Setting column: {col_name} to {row[col_name]}", flush=True)
                    continue

                # Otherwise, None
                result_data[col_name] = None
                # print("No value found for column", col_name, flush=True)

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
