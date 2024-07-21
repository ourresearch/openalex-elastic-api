import re

import requests

from config.entity_config import entity_configs_dict
from config.property_config import property_configs_dict

valid_entities = list(entity_configs_dict.keys())


class Query:
    def __init__(self, query_string, page=1, per_page=25):
        self.query_string = query_string
        self.entity = self.detect_entity()
        self.columns = self.detect_columns()
        self.valid_columns = self.get_valid_columns()
        self.page = int(page) if page else None
        self.per_page = int(per_page) if per_page else None

    def detect_entity(self):
        pattern = re.compile(r'\b(?:get)\s+(\w+)', re.IGNORECASE)

        match = pattern.search(self.query_string)

        if match:
            entity = match.group(1)
            return entity
        else:
            return None

    def detect_columns(self):
        pattern = re.compile(r'\b(?:return|from|select)\s+columns\s+(.+)', re.IGNORECASE)

        match = pattern.search(self.query_string)
        if match:
            columns = match.group(1)
            return [convert_to_snake_case(col.strip()) for col in columns.split(',')]
        else:
            return None

    def is_valid(self):
        if not self.entity:
            return False

        if self.query_string.strip().lower() == f"get {self.entity}":
            if self.entity in valid_entities:
                return True

        if self.query_string.lower().startswith(f"get {self.entity} return columns"):
            if self.columns and all(col in self.valid_columns for col in self.columns):
                return True

        return False

    @property
    def get_clause(self):
        return f"get {self.entity}" if self.entity else None

    @property
    def columns_clause(self):
        return f"return columns {', '.join(self.columns)}" if self.columns else None

    def old_query(self):
        url = None
        if self.entity and self.columns:
            split_columns = [col.split('.')[0] for col in self.columns]
            columns_formatted = ','.join(split_columns)
            url = f"/{self.entity}?select={columns_formatted}" if self.is_valid() else None
        elif self.entity:
            url = f"/{self.entity}" if self.is_valid() else None

        if url:
            params = []
            if self.page:
                params.append(f"page={self.page}")
            if self.per_page:
                params.append(f"per_page={self.per_page}")
            if params:
                if '?' in url:
                    url += '&' + '&'.join(params)
                else:
                    url += '?' + '&'.join(params)
        return url

    def oql_query(self):
        if self.get_clause and self.columns_clause:
            return f"{self.get_clause} {self.columns_clause}" if self.is_valid() else None
        elif self.get_clause:
            return self.get_clause if self.is_valid() else None
        else:
            return None

    def autocomplete(self):
        query_lower = self.query_string.lower().replace('%20', ' ').strip()

        if not query_lower or len(query_lower) < 5:
            return self.suggest_verbs()

        if query_lower.startswith("get"):
            parts = query_lower.split()
            if len(parts) == 1:
                return self.suggest_entities()
            elif len(parts) == 2:
                return self.handle_entity_part(parts)
            elif len(parts) > 2:
                if self.match_partial_command(parts, 2, "return", ["columns"]):
                    if len(parts) == 3:
                        return {"type": "verb", "suggestions": ["return columns"]}
                    elif len(parts) == 4:
                        if parts[3] == "columns":
                            return self.suggest_columns(parts)
                        else:
                            return {"type": "verb", "suggestions": ["columns"]}
                    elif len(parts) > 4 and parts[3] == "columns":
                        return self.suggest_columns(parts)
                return self.handle_columns_part(parts)

        return {"type": "unknown", "suggestions": []}

    def suggest_verbs(self):
        return {"type": "verb", "suggestions": ["get"]}

    def suggest_entities(self):
        return {"type": "entity", "suggestions": valid_entities}

    def handle_entity_part(self, parts):
        if parts[1] in valid_entities:
            return {"type": "verb", "suggestions": ["return columns"]}
        else:
            partial_entity = parts[1]
            filtered_suggestions = [entity for entity in valid_entities if entity.startswith(partial_entity)]
            return {"type": "entity", "suggestions": filtered_suggestions}

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
            typed_columns = [convert_to_snake_case(col.strip()) for col in columns_part.split(',') if col.strip()]
            available_columns = [col for col in valid_cols if col not in typed_columns]

            if ',' in columns_part:
                last_comma_index = columns_part.rindex(',')
                partial_column = columns_part[last_comma_index + 1:].strip()
                filtered_suggestions = [column for column in available_columns if column.startswith(partial_column)]
            else:
                partial_column = columns_part
                filtered_suggestions = [column for column in available_columns if column.startswith(partial_column)]
            return {"type": "column", "suggestions": filtered_suggestions}
        return {"type": "unknown", "suggestions": []}

    def match_partial_command(self, parts, index, command, next_options):
        if parts[index].startswith(command[:len(parts[index])]):
            if len(parts) == index + 1 or (
                    len(parts) > index + 1 and any(parts[index + 1].startswith(option) for option in next_options)):
                return True
        return False

    def convert_to_snake_case(name):
        return name.strip().replace(' ', '_').lower()

    def execute(self):
        url = f"https://api.openalex.org/{self.old_query()}"
        r = requests.get(url)
        return r.json()

    def get_valid_columns(self):
        if self.entity and self.entity in entity_configs_dict:
            return property_configs_dict[self.entity].keys()
        else:
            return []

    def to_dict(self):
        return {
            "query": {
                "original": self.query_string,
                "oql": self.oql_query(),
                "v1": self.old_query()
            },
            "is_valid": self.is_valid(),
            "autocomplete": self.autocomplete()
        }


def convert_to_snake_case(name):
    return name.strip().replace(' ', '_').lower()