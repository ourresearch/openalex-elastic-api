import re

from combined_config import all_entities_config
from oql.redshift import RedshiftQueryHandler

valid_entities = list(all_entities_config.keys())


class Query:
    def __init__(self, query_string, page=1, per_page=25):
        self.verbs = {
            "select": "get",
        }
        self.query_string = self.clean_query_string(query_string)
        self.split_string = self.split_raw_string()
        self.oql_query_parts = self.get_oql_query_parts
        self.entity = self.detect_entity()
        self.filter_by = self.detect_filter_by()
        self.columns = self.detect_return_columns()
        self.display_columns = self.detect_display_columns()
        self.sort_by_column, self.sort_by_order = self.detect_sort_by()
        self.valid_columns = self.get_valid_columns()
        self.valid_sort_columns = self.get_valid_sort_columns()
        self.page = int(page) if page else None
        self.per_page = int(per_page) if per_page else None
        self.oql_json = self.parse_oql_to_json()

    @staticmethod
    def clean_query_string(query_string):
        # remove double spaces
        query_string = re.sub(r"\s+", " ", query_string)
        # remove leading and trailing spaces
        query_string = query_string.strip()
        # remove newlines
        query_string = query_string.replace("\n", " ")
        query_string = query_string.replace("\\n", " ")
        print(f"cleaned query string: {query_string}")
        return query_string

    # detection methods
    def detect_entity(self):
        return self._detect_pattern(r"\b(?:get)\s+([\w-]+)", group=1)

    def detect_filter_by(self):
        return self._detect_pattern(
            r"\b(?:where)\s+((?:(?!\b(?:return|sort by)\b).)+)", group=1
        )

    def detect_return_columns(self):
        pattern = r"\breturn\s+(.+)"
        return_columns = self._detect_pattern(pattern, group=1)
        if return_columns:
            return_columns = [
                convert_to_snake_case(col.strip()) for col in return_columns.split(",")
            ]
            return return_columns
        return None

    def detect_display_columns(self):
        pattern = r"\breturn\s+(.+)"
        columns = self._detect_pattern(pattern, group=1)
        if columns:
            return [convert_to_snake_case(col.strip()) for col in columns.split(",")]
        else:
            return self.default_columns()

    def detect_sort_by(self):
        match = re.search(
            r"\b(?:sort by)\s+(\w+(?:\([\w]+\))?)(?:\s+(asc|desc))?", self.query_string, re.IGNORECASE
        )
        if match:
            sort_by = match.group(1)
            sort_order = match.group(2)

            # Convert column name to snake_case
            if sort_by and sort_by in self.get_valid_sort_columns():
                sort_column = convert_to_snake_case(sort_by)
            elif self.entity and self.entity == "works":
                sort_column = "cited_by_count"
            else:
                sort_column = "display_name"

            # Determine the sort order, default to 'asc' if type is string or 'desc' if type is number
            if sort_order:
                sort_order = sort_order.lower()
                if sort_order not in ["asc", "desc"]:
                    sort_order = "asc"
            else:
                print(self.property_type(sort_column))
                if self.property_type(sort_column) == "number":
                    sort_order = "desc"
                else:
                    sort_order = "asc"

            return sort_column, sort_order
        elif self.entity and self.entity == "works":
            return "cited_by_count", "desc"
        else:
            return "display_name", "asc"

    def detect_using(self):
        return self._detect_pattern(r"\b(?:using)\s+(\w+)", group=1)

    def _detect_pattern(self, pattern, group=0):
        match = re.search(pattern, self.query_string, re.IGNORECASE)
        return match.group(group).strip() if match else None

    # validation methods
    def is_valid(self):
        for item in [
            self._is_valid_simple_get,
            self._is_valid_get_with_filter_by,
            self._is_valid_get_with_filter_by_and_columns,
            self._is_valid_get_with_columns,
            self._is_valid_get_with_sort,
            self._is_valid_get_with_sort_and_columns,
            self._is_valid_get_with_filter_sort_and_columns,
        ]:
            if item():
                print(f"function that is valid: {item.__name__}")
        return any(
            [
                self._is_valid_simple_get(),
                self._is_valid_get_with_filter_by(),
                self._is_valid_get_with_filter_by_and_columns(),
                self._is_valid_get_with_columns(),
                self._is_valid_get_with_sort(),
                self._is_valid_get_with_sort_and_columns(),
                self._is_valid_get_with_filter_sort_and_columns(),
            ]
        )

    def _is_valid_simple_get(self):
        return (
            self.query_string.strip().lower() == f"{self.verbs['select']} {self.entity}"
            or self.query_string.strip().lower()
            == f"using works {self.verbs['select']} {self.entity}"
        ) and self.entity in valid_entities

    def _is_valid_get_with_filter_by(self):
        columns = self.convert_filter_by().keys() if self.filter_by else []
        return (
            (
                self.query_string.lower().startswith(
                    f"{self.verbs['select']} {self.entity} where"
                )
                or self.query_string.lower().startswith(
                    f"using works {self.verbs['select']} {self.entity} where"
                )
            )
            and self.filter_by
            and (
                self.query_string.lower()
                == f"{self.verbs['select']} {self.entity} where {self.filter_by.lower()}"
                or self.query_string.lower()
                == f"using works {self.verbs['select']} {self.entity} where {self.filter_by.lower()}"
            )
            and all(col in self.valid_columns for col in columns)
            and self.entity in valid_entities
        )

    def _is_valid_get_with_filter_by_and_columns(self):
        columns = self.convert_filter_by().keys() if self.filter_by else []
        return (
            (
                self.query_string.lower().startswith(
                    f"{self.verbs['select']} {self.entity} where"
                )
                or self.query_string.lower().startswith(
                    f"using works {self.verbs['select']} {self.entity} where"
                )
            )
            and self.filter_by
            and self.columns
            and all(col in self.valid_columns for col in self.columns)
            and (
                self.query_string.lower()
                == f"{self.verbs['select']} {self.entity} where {self.filter_by.lower()} return {', '.join(self.display_columns)}"
                or self.query_string.lower()
                == f"using works {self.verbs['select']} {self.entity} where {self.filter_by.lower()} return {', '.join(self.display_columns)}"
            )
            and all(col in self.valid_columns for col in columns)
            and self.entity in valid_entities
        )

    def _is_valid_get_with_columns(self):
        return (
            (
                self.query_string.lower().startswith(
                    f"{self.verbs['select']} {self.entity} return"
                )
                or self.query_string.lower().startswith(
                    f"using works {self.verbs['select']} {self.entity} return"
                )
            )
            and self.columns
            and all(col in self.valid_columns for col in self.columns)
            and (
                self.query_string.lower()
                == f"{self.verbs['select']} {self.entity} return {', '.join(self.display_columns)}"
                or self.query_string.lower()
                == f"using works {self.verbs['select']} {self.entity} return {', '.join(self.display_columns)}"
            )
            and self.entity in valid_entities
        )

    def _is_valid_get_with_sort(self):
        return (
            (
                self.query_string.lower().startswith(
                    f"{self.verbs['select']} {self.entity} sort by"
                )
                or self.query_string.lower().startswith(
                    f"using works {self.verbs['select']} {self.entity} sort by"
                )
            )
            and self.sort_by_column
            and self.sort_by_column in self.valid_sort_columns
            and self.sort_by_order
            and not self.columns
            and self.entity in valid_entities
            and (
                self.query_string.lower()
                == f"{self.verbs['select']} {self.entity} sort by {self.sort_by_column}"
                or self.query_string.lower()
                == f"{self.verbs['select']} {self.entity} sort by {self.sort_by_column} {self.sort_by_order}"
                or self.query_string.lower()
                == f"using works {self.verbs['select']} {self.entity} sort by {self.sort_by_column}"
                or self.query_string.lower()
                == f"using works {self.verbs['select']} {self.entity} sort by {self.sort_by_column} {self.sort_by_order}"
            )
        )

    def _is_valid_get_with_sort_and_columns(self):
        return (
            (
                self.query_string.lower().startswith(
                    f"{self.verbs['select']} {self.entity} sort by"
                )
                or self.query_string.lower().startswith(
                    f"using works {self.verbs['select']} {self.entity} sort by"
                )
            )
            and self.sort_by_column
            and self.sort_by_column in self.valid_sort_columns
            and self.columns
            and all(col in self.valid_columns for col in self.columns)
            and (
                self.query_string.lower()
                == f"{self.verbs['select']} {self.entity} sort by {self.sort_by_column} return {', '.join(self.display_columns)}"
                or self.query_string.lower()
                == f"{self.verbs['select']} {self.entity} sort by {self.sort_by_column} {self.sort_by_order} return {', '.join(self.display_columns)}"
                or self.query_string.lower()
                == f"using works {self.verbs['select']} {self.entity} sort by {self.sort_by_column} return {', '.join(self.display_columns)}"
                or self.query_string.lower()
                == f"using works {self.verbs['select']} {self.entity} sort by {self.sort_by_column} {self.sort_by_order} return {', '.join(self.display_columns)}"
            )
            and self.entity in valid_entities
        )

    def _is_valid_get_with_filter_sort_and_columns(self):
        return (
            (
                self.query_string.lower().startswith(
                    f"{self.verbs['select']} {self.entity} where"
                )
                or self.query_string.lower().startswith(
                    f"using works {self.verbs['select']} {self.entity} where"
                )
            )
            and self.filter_by
            and self.columns
            and all(col in self.valid_columns for col in self.columns)
            and (
                self.query_string.lower()
                == f"{self.verbs['select']} {self.entity} where {self.filter_by.lower()} sort by {self.sort_by_column} return {', '.join(self.display_columns)}"
                or self.query_string.lower()
                == f"{self.verbs['select']} {self.entity} where {self.filter_by.lower()} sort by {self.sort_by_column} {self.sort_by_order} return {', '.join(self.display_columns)}"
                or self.query_string.lower()
                == f"using works {self.verbs['select']} {self.entity} where {self.filter_by.lower()} sort by {self.sort_by_column} return {', '.join(self.display_columns)}"
                or self.query_string.lower()
                == f"using works {self.verbs['select']} {self.entity} where {self.filter_by.lower()} sort by {self.sort_by_column} {self.sort_by_order} return {', '.join(self.display_columns)}"
            )
            and self.entity in valid_entities
        )

    # conversion methods
    def convert_filter_by(self):
        filters_dict = {}
        filters = self.filter_by.split(",") if self.filter_by else []

        for filter_condition in filters:
            parts = filter_condition.strip().split()
            if len(parts) == 3 and parts[1].lower() == "is":
                key = parts[0]
                if key == "institution":
                    key = "id"
                value = parts[2]
                filters_dict[key] = value

        return filters_dict

    # clause properties
    @property
    def using_clause(self):
        if self.detect_using():
            return f"using {self.detect_using()}"
        else:
            return "using works"

    @property
    def get_clause(self):
        return f"{self.verbs['select']} {self.entity}" if self.entity else None

    @property
    def filter_by_clause(self):
        return f"where {self.filter_by}" if self.filter_by else None

    @property
    def return_columns_clause(self):
        return (
            f"return {', '.join(self.display_columns)}"
            if self.display_columns
            else None
        )

    @property
    def sort_by_clause(self):
        return f"sort by {self.sort_by_column} {self.sort_by_order}"

    # query methods
    def old_query(self):
        if not self.is_valid():
            return None

        url = f"/{self.entity}"
        if self.columns:
            columns_formatted = ",".join([col.split(".")[0] for col in self.columns])
            url += f"?select={columns_formatted}"

        params = []
        if self.page:
            params.append(f"page={self.page}")
        if self.per_page:
            params.append(f"per_page={self.per_page}")
        if self.sort_by_column:
            if self.sort_by_order == "asc":
                params.append(f"sort={self.sort_by_column}:asc")
            elif self.sort_by_order == "desc":
                params.append(f"sort={self.sort_by_column}:desc")
        if self.filter_by:
            filter_string = ""
            for key, value in self.convert_filter_by().items():
                # create comma separated list but do not include the last comma
                filter_string += f"{key}:{value},"
            filter_string = filter_string[:-1]
            params.append(f"filter={filter_string}")

        if params:
            url += "&" + "&".join(params) if "?" in url else "?" + "&".join(params)

        print(f"old query: {url}")

        return url

    def oql_query(self):
        if not self.is_valid():
            return None

        if self.get_clause and self.filter_by_clause:
            combined_get_and_filter = f"{self.get_clause} {self.filter_by_clause}"
        else:
            combined_get_and_filter = self.get_clause

        clauses = filter(
            None,
            [
                self.using_clause,
                combined_get_and_filter,
                self.sort_by_clause,
                self.return_columns_clause,
            ],
        )
        joined_clauses = "\n".join(clause for clause in clauses if clause)
        return joined_clauses

    def execute(self):
        redshift_handler = RedshiftQueryHandler(
            entity=self.entity,
            sort_by_column=self.sort_by_column,
            sort_by_order=self.sort_by_order,
            filter_by=self.convert_filter_by(),
            return_columns=self.columns,
            valid_columns=self.valid_columns
        )
        results = redshift_handler.redshift_query()
        json_data = self.format_results_as_json(results)
        return json_data

    def format_results_as_json(self, results):
        json_data = {"results": []}
        columns = self.columns or self.default_columns()
        for r in results:
            if r.id == "works/W4285719527":
                # deleted work, skip
                continue
            result_data = {}
            for column in columns:
                if column == "type":
                    value = r.type_formatted
                elif column == "country_code":
                    value = r.country_code_formatted
                elif column == "mean(fwci)":
                    value = r.mean_fwci
                else:
                    value = getattr(r, column, None)
                result_data[column] = value
            result_data["id"] = r.id
            json_data["results"].append(result_data)
        return json_data

    def get_valid_columns(self):
        return (
            all_entities_config[self.entity]['columns'].keys()
            if self.entity and self.entity in all_entities_config
            else []
        )

    def default_columns(self):
        if self.entity and self.entity in all_entities_config:
            return all_entities_config[self.entity]["showOnTablePage"]
        else:
            return []

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

    def split_raw_string(self):
        split_string = [self.clean_query_string(x).lower() for x in self.query_string.split(";")]

        return [x for x in split_string if x]

    @property
    def get_oql_query_parts(self):
        oql_parts = []
        for query_part in self.split_string:
            if query_part.startswith("get works"):
                oql_parts.append("get works")
                continue
            elif query_part.startswith("summarize"):
                oql_parts.append("summarize")
                continue
            elif query_part.startswith("sort by"):
                oql_parts.append("sort by")
                continue
            elif query_part.startswith("return"):
                oql_parts.append("return")
                continue
        return oql_parts

    @property
    def quick_validate_oql(self):

        if len(set(self.oql_query_parts)) == len(self.split_string) and "get works" in self.oql_query_parts:
            return True
        else:
            return False

    def return_as_expression_list(self, all_where_clauses):
        expression_list = []
        for where_clause in all_where_clauses:
            if " is " in where_clause:
                split_where_clause = where_clause.split(" is ")

                expression_list.append({
                    "expression_type": "rule",
                    "prop_id": split_where_clause[0],
                    "operator": "is",
                    "value": split_where_clause[1]
                })
        return expression_list


    def get_works_where_json(self):
        get_works_clause = [x for x in self.split_string if x.startswith("get works")][0]

        works_where_json = {
            "expressions": {
                "expression_type": "list",
                "operator": "and",
                "expressions": []
            },
            "as_string": get_works_clause
        }

        if " where " in get_works_clause:
            where_clauses = get_works_clause.split(" where ")[1].split(" and ")

            works_where_json["expressions"]["expressions"] = self.return_as_expression_list(where_clauses)


        return works_where_json


    def get_summary_json_parts(self):
        summarize_clause = [x for x in self.split_string if x.startswith("summarize")][0]

        summarize_by = None

        summarize_by_where = {
            "expressions": {
                "expression_type": "list",
                "operator": "and",
                "expressions": []
            }, 
            "as_string": summarize_clause
        }

        if "summarize by " in summarize_clause:
            summarize_by_clause = summarize_clause.split("summarize by ")[1]

            if " where " in summarize_by_clause:
                summarize_by_where_clause = summarize_by_clause.split(" where ")

                # first part is entity to summarize by, second part is filter
                summarize_by = summarize_by_where_clause[0]
                where_clauses = summarize_by_where_clause[1].split(" and ")

                # get all expressions
                summarize_by_where["expressions"]["expressions"] = self.return_as_expression_list(where_clauses)

            else:
                summarize_by = summarize_by_clause

        return summarize_by, summarize_by_where


    def parse_oql_to_json(self):
        if self.quick_validate_oql:
            final_json = {
              "json_query": {
                "get_works_where": self.get_works_where_json()},
                "oql": "; ".join(self.split_string) + ";",
                "old_style": "string"
            }
            if "summarize" in self.oql_query_parts:
                summary_json_parts = self.get_summary_json_parts()
                final_json["json_query"]["summarize"] = True

                if summary_json_parts[0]:
                    final_json["json_query"]["summarize_by"] = summary_json_parts[0].strip()
                    final_json["json_query"]["summarize_by_where"] = summary_json_parts[1]

            if 'sort by' in self.oql_query_parts:
                final_json["json_query"]["sort_by"] = {"column_id": self.sort_by_column,
                                                       "direction": self.sort_by_order}

            final_json["json_query"]["return"] = [x.replace(";", "") for x in self.display_columns]
        else:
            final_json = None
        return final_json

    def to_dict(self):
        return {
            "query": {
                "original": self.query_string,
                "oql": self.oql_query(),
                "v1": self.old_query(),
                "jsonQuery": self.oql_json,
            },
            "is_valid": self.is_valid(),
        }


def convert_to_snake_case(name):
    return name.strip().replace(" ", "_").lower()
