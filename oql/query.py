import re

import requests

valid_columns = ['id', 'display_name', 'title', 'publication_year', 'cited_by_count']
valid_entities = ['works', 'authors', 'institutions', 'sources', 'topics']


class Query:
    def __init__(self, query_string):
        self.query_string = query_string
        self.entity = self.detect_entity()
        self.columns = self.detect_columns()

    def detect_entity(self):
        pattern = re.compile(r'\b(?:using|from|select)\s+(\w+)', re.IGNORECASE)

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

        if self.query_string.strip().lower() == f"using {self.entity}":
            if self.entity in valid_entities:
                return True

        if self.query_string.lower().startswith(f"using {self.entity} return columns"):
            if self.columns and all(col in valid_columns for col in self.columns):
                return True

        return False

    @property
    def use_clause(self):
        return f"using {self.entity}" if self.entity else None

    @property
    def columns_clause(self):
        return f"return columns {', '.join(self.columns)}" if self.columns else None

    def old_query(self):
        if self.entity and self.columns:
            columns_formatted = ','.join(self.columns)
            return f"/{self.entity}?select={columns_formatted}" if self.is_valid() else None
        elif self.entity:
            return f"/{self.entity}" if self.is_valid() else None

    def oql_query(self):
        if self.use_clause and self.columns_clause:
            return f"{self.use_clause} {self.columns_clause}" if self.is_valid() else None
        elif self.use_clause:
            return self.use_clause if self.is_valid() else None
        else:
            return None

    def autocomplete(self):
        query_lower = self.query_string.lower().strip()

        if not query_lower or len(query_lower) < 5:
            return {"type": "verb", "suggestions": ["using"]}

        if query_lower.startswith("using"):
            parts = query_lower.split()
            if len(parts) == 1:
                return {"type": "entity", "suggestions": valid_entities}
            elif len(parts) == 2:
                if parts[1] in valid_entities:
                    return {"type": "verb", "suggestions": ["return columns"]}
                else:
                    partial_entity = parts[1]
                    filtered_suggestions = [entity for entity in valid_entities if entity.startswith(partial_entity)]
                    return {"type": "entity", "suggestions": filtered_suggestions}
            elif len(parts) > 2:
                if len(parts) == 3 or (len(parts) == 4 and parts[3] != "columns"):
                    return {"type": "verb", "suggestions": ["return columns"]}
                elif len(parts) >= 4 and parts[3] == "columns" and self.is_valid():
                    return {"type": "none", "suggestions": []}
                elif len(parts) >= 4 and parts[3] == "columns":
                    partial_column = " ".join(parts[4:])
                    filtered_suggestions = [column for column in valid_columns if column.startswith(partial_column)]
                    return {"type": "column", "suggestions": filtered_suggestions}

        return {"type": "unknown", "suggestions": []}

    def execute(self):
        url = f"https://api.openalex.org/{self.old_query()}"
        r = requests.get(url)
        return r.json()

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