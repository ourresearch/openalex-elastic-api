from datetime import datetime, timezone
import requests
import copy

from sqlalchemy.engine.row import Row

import settings
from combined_config import all_entities_config
from oql.elastic import ElasticQueryHandler
from oql.redshift import RedshiftQueryHandler
from oql.models import get_entity_class, is_model_property, is_model_hybrid_property


class Query:
    """
    Query object to execute a query and return results. Also sets the defaults for the query.
    """
    def __init__(self, raw_query, use_elastic=False):
        self.query = raw_query
        self.entity = raw_query.get("get_rows", "works")
        self.filter_works = raw_query.get("filter_works", [])
        self.filter_aggs = raw_query.get("filter_aggs", [])
        self.sort_by_column = raw_query.get("sort_by_column", self.default_sort_by_column())
        self.sort_by_order = raw_query.get("sort_by_order", self.default_sort_by_order())
        self.show_columns = self.set_show_columns(raw_query.get("show_columns", []))
        self.show_underlying_works = raw_query.get("show_underlying_works", False)
        self.total_count = 0
        self.works_count = 0
        self.valid_columns = self.get_valid_columns()
        self.valid_sort_columns = self.get_valid_sort_columns()
        self.source = None
        self.use_elastic = use_elastic

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
            valid_columns=self.valid_columns,
            show_underlying_works=self.show_underlying_works
        )

    def execute(self):
        timestamps = {"started": datetime.now(timezone.utc).isoformat()}
        
        print(f"Query.execute(): use_elastic: {self.use_elastic}")
        
        if self.entity == "summary":
            results = self.redshift_handler.execute_summary()
            self.total_count = results["count"]
            json_data = {"results": [results]}
        
        elif self.use_elastic and self.elastic_handler.is_valid():
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

        entity = self.entity if not self.show_underlying_works else "works"

        output_columns = list(set(self.show_columns + ["id"]))
        entity_class = get_entity_class(entity)
        entity_columns_config = all_entities_config[entity]["columns"]
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
                    #print(f"missing redshift column for key: {key}", flush=True)
                    continue
                if hasattr(entity_class, redshift_column) and not is_model_hybrid_property(redshift_column, entity_class):
                    #print(f"Ephemeral Model: Setting column: {key} to {row[key]}", flush=True)
                    setattr(ephemeral_model, redshift_column, row[key])

            # Skip "deleted" works or null author ID
            if ephemeral_model.id == "works/W4285719527" or ephemeral_model.id == "authors/A9999999999":
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
                        print(f"Calling property method for {redshift_column}", flush=True)
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

    def has_lists(self):
        """ Returns true if the query contains filters that use user created lists."""
        user_operators = [
            "matches any item in label",
            "matches every item in label"
        ]

        def does_filter_contain_user_data(filter_):
            if "filters" in filter_:
                return any(does_filter_contain_user_data(f) for f in filter_["filters"])
            return filter_.get("operator") in user_operators

        filters_to_check = (self.query.get("filter_works") or []) + (self.query.get("filter_aggs") or [])
        #print(f"Checking filters: {filters_to_check}", flush=True)
        return any(does_filter_contain_user_data(f) for f in filters_to_check)
    
    def rewrite_query_with_user_data(self, user_id, jwt_token):
        """
        Recursively walk through the query and replace any filters that have label components
        with their equivalents that don't reference user labels.
        """
        def rewrite_filters(filters, case):
            """
            Recursive helper function to rewrite filters.
            case is either "filter_works" or "filter_aggs"
            """
            rewritten_filters = []
            for filter_obj in filters:
                if "join" in filter_obj and "filters" in filter_obj:
                    # Recursive case: rewrite the nested filters
                    rewritten_filter = {
                        "join": filter_obj["join"],
                        "filters": rewrite_filters(filter_obj["filters"], case),
                    }
                    rewritten_filters.append(rewritten_filter)
                else:
                    # Terminal case: check if the operator matches a label condition
                    operator = filter_obj.get("operator")
                    # print(f"looking at operator: {operator}")
                    if operator in ["matches any item in label", "matches every item in label"]:
                        print("Found user data in query")
                        label_id = filter_obj.get("value")
                        #label = Collection.get_collection_by_id(label_id)

                        headers = {"Authorization": jwt_token}
                        url = f"{settings.USERS_API_URL}/user/{user_id}/collections/{label_id}"
                        #print(f"Fetching label data from {url}")
                        response = requests.get(url, headers=headers)
                        label = response.json()

                        if not label:
                            raise ValueError(f"Label with ID {label_id} not found.")
                        if not label["ids"]:
                            raise ValueError(f"Label {label_id} contains no items.")

                        #print("Label Data:")
                        #print(label)

                        # Determine the join type based on the operator
                        join_type = "or" if operator == "matches any item in label" else "and"

                        works_id_keys = {
                            "authors": "authorships.author.id",
                            "continents": "authorships.institutions.continent",
                            "countries": "authorships.institutions.country",
                            "domains": "primary_topic.domain.id",
                            "fields": "primary_topic.field.id",
                            "funders": "grants.funder",
                            "institution-types": "authorships.institutions.type",
                            "institutions": "authorships.institutions.lineage",
                            "keywords": "keywords.id",
                            "langauges": "language",
                            "licenses": "MISSING",
                            "publishers": "MISSING",
                            "sdgs": "sustainable_developement_goals.id",
                            "sources": "primary_location.source.id",
                            "subfields": "primary_topic.subfield.id",
                            "topics": "primary_topic.id",
                            "work-types": "type",
                        }

                        column_id = works_id_keys[label["entity_type"]] if case == "filter_works" else "id"

                        # Construct the rewritten filters for this label
                        rewritten_label_filter = {
                            "join": join_type,
                            "filters": [
                                {
                                    "column_id": column_id,
                                    "value": id_value,
                                }
                                for id_value in label["ids"]
                            ],
                        }
                        rewritten_filters.append(rewritten_label_filter)
                    else:
                        rewritten_filters.append(filter_obj)

            return rewritten_filters

        # Start rewriting from self.query
        query_rewritten = copy.deepcopy(self.query)  # Create a copy of the original query

        for case in ["filter_works", "filter_aggs"]:
            if case in query_rewritten:
                query_rewritten[case] = rewrite_filters(query_rewritten[case], case)

        return query_rewritten

    def extract_filter_keys(self):
        """
        Extracts filter keys from both "filter_works" and "filter_aggs" into a flat list.
        """
        keys = []
        def walk_filters(filters, entity):
            for f in filters:
                # If this is a composite filter with a join and nested filters:
                if "join" in f and "filters" in f:
                    walk_filters(f["filters"], entity)
                else:
                    if "column_id" in f:
                        keys.append(f"{entity}.{f['column_id']}")

        for key in ["filter_works", "filter_aggs"]:
            key_type = "works" if key == "filter_works" else self.entity
            if key in self.query and isinstance(self.query[key], list):
                walk_filters(self.query[key], key_type)
        return keys if keys else None

    def has_nested_boolean(self):
        """
        Returns true if the query contains nested boolean logic.
        """
        # For now, a simple check: if any filter has a "join" key, return True.
        for key in ["filter_works", "filter_aggs"]:
            if key in self.query and isinstance(self.query[key], list):
                for f in self.query[key]:
                    if "join" in f:
                        return True
        return False   

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
            "show_underlying_works": self.show_underlying_works,
        }


def convert_to_snake_case(name):
    return name.strip().replace(" ", "_").lower()
