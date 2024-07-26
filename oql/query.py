import re
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse

import requests

from config.entity_config import entity_configs_dict
from config.property_config import property_configs_dict

valid_entities = list(entity_configs_dict.keys())


class Query:
    def __init__(self, query_string, page=1, per_page=25):
        self.verbs = {
            "select": "list",
        }
        self.query_string = query_string
        self.entity = self.detect_entity()
        self.filter_by = self.detect_filter_by()
        self.columns = self.detect_return_columns()
        self.sort_by = self.detect_sort_by()
        self.valid_columns = self.get_valid_columns()
        self.valid_sort_columns = self.get_valid_sort_columns()
        self.page = int(page) if page else None
        self.per_page = int(per_page) if per_page else None

    # detection methods
    def detect_entity(self):
        return self._detect_pattern(r"\b(?:list)\s+(\w+)", group=1)

    def detect_filter_by(self):
        return self._detect_pattern(
            r"\b(?:where)\s+((?:(?!\b(?:return columns|sort by)\b).)+)", group=1
        )

    def detect_return_columns(self):
        columns = self._detect_pattern(r"\b(?:return)\s+columns\s+(.+)", group=1)
        if columns:
            return [convert_to_snake_case(col.strip()) for col in columns.split(",")]
        return None

    def detect_sort_by(self):
        sort_by = self._detect_pattern(r"\b(?:sort by)\s+(\w+)", group=1)
        if sort_by and sort_by in self.get_valid_sort_columns():
            return convert_to_snake_case(sort_by)
        return None

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
            == f"{self.verbs['select']} {self.entity} where {self.filter_by.lower()} return columns {', '.join(self.columns)}"
            and all(col in self.valid_columns for col in columns)
        )

    def _is_valid_get_with_columns(self):
        return (
            self.query_string.lower().startswith(
                f"{self.verbs['select']} {self.entity} return columns"
            )
            and self.columns
            and all(col in self.valid_columns for col in self.columns)
            and self.query_string.lower()
            == f"{self.verbs['select']} {self.entity} return columns {', '.join(self.columns)}"
        )

    def _is_valid_get_with_sort(self):
        return (
            self.query_string.lower().startswith(
                f"{self.verbs['select']} {self.entity} sort by"
            )
            and self.sort_by
            and self.sort_by in self.valid_sort_columns
            and not self.columns
            and self.query_string.lower()
            == f"{self.verbs['select']} {self.entity} sort by {self.sort_by}"
        )

    def _is_valid_get_with_sort_and_columns(self):
        return (
            self.query_string.lower().startswith(
                f"{self.verbs['select']} {self.entity} sort by"
            )
            and self.sort_by
            and self.sort_by in self.valid_sort_columns
            and self.columns
            and all(col in self.valid_columns for col in self.columns)
            and self.query_string.lower()
            == f"{self.verbs['select']} {self.entity} sort by {self.sort_by} return columns {', '.join(self.columns)}"
        )

    # conversion methods
    def convert_filter_by(self):
        filters_dict = {}
        filters = self.filter_by.split(",")

        for filter_condition in filters:
            parts = filter_condition.strip().split()
            if len(parts) == 3 and parts[1].lower() == "is":
                key = parts[0]
                value = parts[2]
                filters_dict[key] = value

        return filters_dict

    # clause properties
    @property
    def get_clause(self):
        return f"{self.verbs['select']} {self.entity}" if self.entity else None

    @property
    def filter_by_clause(self):
        return f"where {self.filter_by}" if self.filter_by else None

    @property
    def return_columns_clause(self):
        return f"return columns {', '.join(self.columns)}" if self.columns else None

    @property
    def sort_by_clause(self):
        return f"sort by {self.sort_by}" if self.sort_by else None

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
        if self.sort_by:
            params.append(f"sort={self.sort_by}")
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
        if not self.is_valid():
            return None

        clauses = filter(
            None,
            [
                self.get_clause,
                self.filter_by_clause,
                self.sort_by_clause,
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
            return {"type": "verb", "suggestions": ["return columns"]}
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
            return {"type": "verb", "suggestions": ["return columns", "sort by"]}
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
                        return {"type": "verb", "suggestions": ["return columns"]}
                elif len(parts) > 5:
                    return {"type": "verb", "suggestions": ["return columns"]}
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

    def get_valid_sort_columns(self):
        if not self.entity or self.entity and self.entity not in entity_configs_dict:
            return []
        return [
            key
            for key, values in property_configs_dict[self.entity].items()
            if "sort" in values.get("actions", [])
        ]

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
