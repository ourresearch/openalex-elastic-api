import re
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse

import requests

from config.entity_config import entity_configs_dict
from config.property_config import property_configs_dict
from config.stats_config import stats_configs_dict

valid_entities = list(entity_configs_dict.keys())


class Query:
    def __init__(self, query_string, page=1, per_page=25):
        self.verbs = {
            "select": "get",
        }
        self.query_string = self.clean_query_string(query_string)
        self.entity = self.detect_entity()
        self.filter_by = self.detect_filter_by()
        self.columns = self.detect_return_columns()
        self.display_columns = self.detect_display_columns()
        self.sort_by_column, self.sort_by_order = self.detect_sort_by()
        self.valid_columns = self.get_valid_columns()
        self.valid_sort_columns = self.get_valid_sort_columns()
        self.page = int(page) if page else None
        self.per_page = int(per_page) if per_page else None

    @staticmethod
    def clean_query_string(query_string):
        # remove double spaces
        query_string = re.sub(r"\s+", " ", query_string)
        # remove leading and trailing spaces
        query_string = query_string.strip()
        # remove newlines
        query_string = query_string.replace("\n", " ")
        return query_string

    # detection methods
    def detect_entity(self):
        return self._detect_pattern(r"\b(?:get)\s+(\w+)", group=1)

    def detect_filter_by(self):
        return self._detect_pattern(
            r"\b(?:where)\s+((?:(?!\b(?:return|sort by)\b).)+)", group=1
        )

    def detect_return_columns(self):
        pattern = r"\breturn\s+(.+)"
        initial_columns = self._detect_pattern(pattern, group=1)
        if initial_columns:
            initial_columns = [
                convert_to_snake_case(col.strip()) for col in initial_columns.split(",")
            ]
            parsed_columns = [self.parse_column(col) for col in initial_columns]
            return [col["column"] for col in parsed_columns]
        return None

    def detect_parsed_columns(self):
        pattern = r"\breturn\s+(.+)"
        initial_columns = self._detect_pattern(pattern, group=1)
        if initial_columns:
            initial_columns = [
                convert_to_snake_case(col.strip()) for col in initial_columns.split(",")
            ]
            parsed_columns = [self.parse_column(col) for col in initial_columns]
            return parsed_columns
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
            r"\b(?:sort by)\s+(\w+)(?:\s+(asc|desc))?", self.query_string, re.IGNORECASE
        )
        if match:
            sort_by = match.group(1)
            sort_order = match.group(2)

            # Convert column name to snake_case
            if sort_by and sort_by in self.get_valid_sort_columns():
                sort_column = convert_to_snake_case(sort_by)
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
        else:
            return "display_name", "asc"

    def detect_using(self):
        return self._detect_pattern(r"\b(?:using)\s+(\w+)", group=1)

    @staticmethod
    def parse_column(column):
        column = column.strip()
        # parse the column to see if it has a stats method like count(referenced_works) or sum(cited_by_count)
        if "(" in column and ")" in column:
            method = column.split("(")[0]
            column_name = column.split("(")[1].split(")")[0]
            return {
                "type": "stats_column",
                "method": method,
                "column": column_name,
            }
        else:
            return {
                "type": "standard_column",
                "method": None,
                "column": column,
            }

    def _detect_pattern(self, pattern, group=0):
        match = re.search(pattern, self.query_string, re.IGNORECASE)
        return match.group(group).strip() if match else None

    # validation methods
    def is_valid(self):
        return any(
            [
                self._is_valid_simple_get(),
                self._is_valid_get_with_filter_by(),
                self._is_valid_get_with_filter_by_and_columns(),
                self._is_valid_get_with_columns(),
                self._is_valid_get_with_sort(),
                self._is_valid_get_with_sort_and_columns(),
            ]
        )

    def _is_valid_simple_get(self):
        return (
            self.query_string.strip().lower() == f"{self.verbs['select']} {self.entity}"
            and self.entity in valid_entities
        )

    def _is_valid_get_with_filter_by(self):
        columns = self.convert_filter_by().keys() if self.filter_by else []
        return (
            self.query_string.lower().startswith(
                f"{self.verbs['select']} {self.entity} where"
            )
            and self.filter_by
            and self.query_string.lower()
            == f"{self.verbs['select']} {self.entity} where {self.filter_by.lower()}"
            and all(col in self.valid_columns for col in columns)
        )

    def _is_valid_get_with_filter_by_and_columns(self):
        columns = self.convert_filter_by().keys() if self.filter_by else []
        return (
            self.query_string.lower().startswith(
                f"{self.verbs['select']} {self.entity} where"
            )
            and self.filter_by
            and self.columns
            and all(col in self.valid_columns for col in self.columns)
            and self.query_string.lower()
            == f"{self.verbs['select']} {self.entity} where {self.filter_by.lower()} return {', '.join(self.display_columns)}"
            and all(col in self.valid_columns for col in columns)
        )

    def _is_valid_get_with_columns(self):
        return (
            self.query_string.lower().startswith(
                f"{self.verbs['select']} {self.entity} return"
            )
            and self.columns
            and all(col in self.valid_columns for col in self.columns)
            and self.query_string.lower()
            == f"{self.verbs['select']} {self.entity} return {', '.join(self.display_columns)}"
        )

    def _is_valid_get_with_sort(self):
        return (
            self.query_string.lower().startswith(
                f"{self.verbs['select']} {self.entity} sort by"
            )
            and self.sort_by_column
            and self.sort_by_column in self.valid_sort_columns
            and self.sort_by_order
            and not self.columns
            and self.query_string.lower()
            == f"{self.verbs['select']} {self.entity} sort by {self.sort_by_column}"
            or self.query_string.lower()
            == f"{self.verbs['select']} {self.entity} sort by {self.sort_by_column} {self.sort_by_order}"
        )

    def _is_valid_get_with_sort_and_columns(self):
        return (
            self.query_string.lower().startswith(
                f"{self.verbs['select']} {self.entity} sort by"
            )
            and self.sort_by_column
            and self.sort_by_column in self.valid_sort_columns
            and self.columns
            and all(col in self.valid_columns for col in self.columns)
            and self.query_string.lower()
            == f"{self.verbs['select']} {self.entity} sort by {self.sort_by_column} return {', '.join(self.columns)}"
            or self.query_string.lower()
            == f"{self.verbs['select']} {self.entity} sort by {self.sort_by_column} {self.sort_by_order} return {', '.join(self.display_columns)}"
        )

    # conversion methods
    def convert_filter_by(self):
        filters_dict = {}
        filters = self.filter_by.split(",")

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

        if "using" in self.query_string:
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

        return url

    def oql_query(self):
        if "using" in self.query_string:
            return self.query_string

        if not self.is_valid():
            return None

        clauses = filter(
            None,
            [
                self.using_clause + "\n",
                self.get_clause + "\n",
                self.filter_by_clause + "\n" if self.filter_by else None,
                self.sort_by_clause + "\n",
                self.return_columns_clause,
            ],
        )
        return " ".join(clauses)

    # suggestion methods
    def autocomplete(self):
        query_lower = self.query_string.lower().replace("%20", " ").strip()

        if not query_lower or len(query_lower) < 3:
            return self.suggest_verbs()

        if query_lower.startswith(self.verbs["select"]):
            parts = query_lower.split()
            if len(parts) == 1:
                return self.suggest_entities()
            elif len(parts) == 2:
                return self.handle_entity_part(parts)
            elif len(parts) > 2:
                return self.handle_extended_parts(parts)

        return {"type": "unknown", "suggestions": []}

    def handle_extended_parts(self, parts):
        if self.match_partial_command(parts, 2, "return", ["columns"]):
            return self._handle_return_columns(parts)
        if self.match_partial_command(parts, 2, "sort", ["by"]):
            return self.handle_sort_part(parts)
        if len(parts) == 3 and "sort by".startswith(parts[2]):
            return {"type": "verb", "suggestions": ["sort by"]}
        return self.handle_columns_part(parts)

    def _handle_return_columns(self, parts):
        if len(parts) == 3:
            return {"type": "verb", "suggestions": ["return"]}
        elif len(parts) == 4 and parts[3] == "columns":
            return self.suggest_columns(parts)
        elif len(parts) > 4 and parts[3] == "columns":
            return self.suggest_columns(parts)
        else:
            return {"type": "verb", "suggestions": ["columns"]}

    def suggest_verbs(self):
        return {"type": "verb", "suggestions": [self.verbs["select"]]}

    def suggest_entities(self):
        return {"type": "entity", "suggestions": valid_entities}

    def handle_entity_part(self, parts):
        if parts[1] in valid_entities:
            return {"type": "verb", "suggestions": ["return", "sort by"]}
        else:
            partial_entity = parts[1]
            filtered_suggestions = [
                entity for entity in valid_entities if entity.startswith(partial_entity)
            ]
            return {"type": "entity", "suggestions": filtered_suggestions}

    def handle_sort_part(self, parts):
        if len(parts) >= 3 and "sort".startswith(parts[2]):
            if len(parts) == 3 or (
                len(parts) == 4 and "by".startswith(parts[3]) and parts[3] != "by"
            ):
                return {"type": "verb", "suggestions": ["sort by"]}
            elif len(parts) >= 4 and parts[3] == "by":
                if len(parts) == 4:
                    return {
                        "type": "sort_column",
                        "suggestions": self.get_valid_sort_columns(),
                    }
                elif len(parts) == 5:
                    sort_suggestions = self.suggest_sort_columns(parts)
                    if sort_suggestions["suggestions"]:
                        return sort_suggestions
                    else:
                        return {"type": "verb", "suggestions": ["return"]}
                elif len(parts) > 5:
                    return {"type": "verb", "suggestions": ["return"]}
        return {"type": "unknown", "suggestions": []}

    def handle_columns_part(self, parts):
        if len(parts) >= 3 and parts[2].startswith("return"):
            if len(parts) == 3 or (len(parts) == 4 and parts[3] != "columns"):
                return {"type": "verb", "suggestions": ["columns"]}
            elif len(parts) >= 4 and parts[3] == "columns":
                return self.suggest_columns(parts)
        return {"type": "unknown", "suggestions": []}

    def suggest_columns(self, parts):
        if self.entity in valid_entities:
            valid_cols = self.get_valid_columns()
            columns_part = " ".join(parts[4:])
            typed_columns = [
                convert_to_snake_case(col.strip())
                for col in columns_part.split(",")
                if col.strip()
            ]
            available_columns = [col for col in valid_cols if col not in typed_columns]

            if "," in columns_part:
                last_comma_index = columns_part.rindex(",")
                partial_column = columns_part[last_comma_index + 1 :].strip()
                filtered_suggestions = [
                    column
                    for column in available_columns
                    if column.startswith(partial_column)
                ]
            else:
                partial_column = columns_part
                filtered_suggestions = [
                    column
                    for column in available_columns
                    if column.startswith(partial_column)
                ]

            return {"type": "column", "suggestions": filtered_suggestions}
        return {"type": "unknown", "suggestions": []}

    def suggest_sort_columns(self, parts):
        if self.entity in valid_entities:
            valid_sort_cols = self.get_valid_sort_columns()
            sort_part = " ".join(parts[4:])
            partial_sort_column = convert_to_snake_case(sort_part.strip())
            filtered_suggestions = [
                column
                for column in valid_sort_cols
                if column.startswith(partial_sort_column)
            ]
            return {"type": "sort_column", "suggestions": filtered_suggestions}
        return {"type": "unknown", "suggestions": []}

    # utility methods
    def match_partial_command(self, parts, index, command, next_options):
        if command.startswith(parts[index]):
            if len(parts) == index + 1:
                return True
            elif len(parts) > index + 1:
                return any(
                    option.startswith(parts[index + 1]) for option in next_options
                )
        return False

    def execute(self):
        url = f"https://api.openalex.org/{self.old_query()}"
        parsed_url = urlparse(url)
        query_params = parse_qs(parsed_url.query)
        select_params = (
            query_params.get("select", [""])[0].split(",")
            if "select" in query_params
            else []
        )

        if select_params and "id" not in select_params:
            select_params.append("id")
            query_params["select"] = ",".join(select_params)

        new_query_string = urlencode(query_params, doseq=True)
        new_url = urlunparse(
            (
                parsed_url.scheme,
                parsed_url.netloc,
                parsed_url.path,
                parsed_url.params,
                new_query_string,
                parsed_url.fragment,
            )
        )

        r = requests.get(new_url)
        return r.json()

    def get_valid_columns(self):
        return (
            property_configs_dict[self.entity].keys()
            if self.entity and self.entity in entity_configs_dict
            else []
        )

    def default_columns(self):
        return entity_configs_dict[self.entity]["rowsToShowOnTablePage"]

    def get_valid_sort_columns(self):
        if not self.entity or self.entity and self.entity not in entity_configs_dict:
            return []
        return [
            key
            for key, values in property_configs_dict[self.entity].items()
            if "sort" in values.get("actions", [])
        ]

    def property_type(self, column):
        for property_config in property_configs_dict.get(self.entity, {}).values():
            if property_config.get("id", "") == column:
                return property_config.get("newType", "string")

    def to_dict(self):
        return {
            "query": {
                "original": self.query_string,
                "oql": self.oql_query(),
                "v1": self.old_query(),
            },
            "is_valid": self.is_valid(),
            "autocomplete": self.autocomplete(),
        }


def convert_to_snake_case(name):
    return name.strip().replace(" ", "_").lower()
