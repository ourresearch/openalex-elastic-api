import datetime
from abc import ABC, abstractmethod

from elasticsearch_dsl import Q

from core.exceptions import APIQueryParamsError
from core.search import search_records


class Field(ABC):
    def __init__(self, param, custom_es_field=None):
        self.param = param
        self.custom_es_field = custom_es_field
        self.value = None

    @abstractmethod
    def build_query(self, s):
        return s

    def validate(self, query):
        pass

    def es_field(self) -> str:
        if self.custom_es_field:
            field = self.custom_es_field
        elif "." in self.param:
            field = self.param.replace(".", "__")
        else:
            field = self.param
        return field

    def es_sort_field(self):
        if self.custom_es_field:
            field = self.custom_es_field.replace("__", ".")
        elif "publisher" in self.param or self.param == "display_name":
            field = f"{self.param}.keyword"
        else:
            field = self.param.replace("__", ".")
        return field


class BooleanField(Field):
    def build_query(self, s):
        self.validate(self.value)
        if self.value == "null":
            s = s.exclude("exists", field=self.es_field())
        elif self.value == "!null":
            s = s.filter("exists", field=self.es_field())
        else:
            kwargs = {self.es_field(): self.value.lower()}
            s = s.filter("term", **kwargs)
        return s

    def validate(self, query):
        valid_values = ["null", "!null", "true", "false"]
        query = query.lower().strip()
        if query not in valid_values:
            raise APIQueryParamsError(
                f"Value for {self.param} must be true, false null, or !null: not {query}"
            )


class DateField(Field):
    def build_query(self, s):
        if "<" in self.value:
            query = self.value[1:]
            self.validate(query)
            kwargs = {self.es_field(): {"lt": query}}
            s = s.filter("range", **kwargs)
        elif ">" in self.value:
            query = self.value[1:]
            self.validate(query)
            kwargs = {self.es_field(): {"gt": query}}
            s = s.filter("range", **kwargs)
        elif self.param == "to_publication_date":
            self.validate(self.value)
            kwargs = {self.es_field(): {"lte": self.value}}
            s = s.filter("range", **kwargs)
        elif self.param == "from_publication_date":
            self.validate(self.value)
            kwargs = {self.es_field(): {"gte": self.value}}
            s = s.filter("range", **kwargs)
        elif self.value == "null":
            s = s.exclude("exists", field=self.es_field())
        else:
            self.validate(self.value)
            kwargs = {self.es_field(): self.value}
            s = s.filter("term", **kwargs)
        return s

    def validate(self, query):
        try:
            datetime.datetime.strptime(query, "%Y-%m-%d")
        except ValueError:
            raise APIQueryParamsError(
                f"Value for param {self.param} must be a date in format 2020-05-17."
            )


class OpenAlexIDField(Field):
    def build_query(self, s):
        if self.value == "null":
            field_name = self.es_field()
            field_name = field_name.replace("__", ".")
            s = s.exclude("exists", field=field_name)
        elif self.value == "!null":
            field_name = self.es_field()
            field_name = field_name.replace("__", ".")
            s = s.filter("exists", field=field_name)
        elif self.value.startswith("!"):
            query = self.value[1:]
            kwargs = {self.es_field(): query}
            s = s.exclude("term", **kwargs)
        elif "https://openalex.org/" in self.value:
            kwargs = {self.es_field(): self.value}
            s = s.filter("term", **kwargs)
        else:
            query = f"https://openalex.org/{self.value.upper()}"
            kwargs = {self.es_field(): query}
            s = s.filter("term", **kwargs)
        return s

    def es_field(self) -> str:
        if self.custom_es_field:
            field = self.custom_es_field
        elif "." in self.param:
            field = self.param.replace(".", "__") + "__lower"
        else:
            field = self.param + "__lower"
        return field


class PhraseField(Field):
    def build_query(self, s):
        if self.value == "null":
            field_name = self.es_field()
            field_name = field_name.replace("__", ".")
            s = s.exclude("exists", field=field_name)
        elif self.value == "!null":
            field_name = self.es_field()
            field_name = field_name.replace("__", ".")
            s = s.filter("exists", field=field_name)
        elif self.value.startswith("!"):
            query = self.value[1:]
            kwargs = {self.es_field(): query}
            s = s.exclude("match_phrase", **kwargs)
        else:
            kwargs = {self.es_field(): self.value}
            s = s.filter("match_phrase", **kwargs)
        return s

    def es_field(self) -> str:
        if self.custom_es_field:
            field = self.custom_es_field
        elif "." in self.param:
            field = self.param.replace(".", "__") + "__lower"
        else:
            field = self.param + "__lower"
        return field


class RangeField(Field):
    def build_query(self, s):
        if "<" in self.value:
            query = self.value[1:]
            self.validate(query)
            kwargs = {self.es_field(): {"lt": int(query)}}
            s = s.filter("range", **kwargs)
        elif ">" in self.value:
            query = self.value[1:]
            self.validate(query)
            kwargs = {self.es_field(): {"gt": int(query)}}
            s = s.filter("range", **kwargs)
        elif "-" in self.value:
            values = self.value.strip().split("-")
            left_value = values[0]
            right_value = values[1]
            self.validate(left_value)
            self.validate(right_value)
            kwargs = {self.es_field(): {"gt": int(left_value), "lt": int(right_value)}}
            s = s.filter("range", **kwargs)
        elif self.value == "null":
            s = s.exclude("exists", field=self.es_field())
        else:
            self.validate(self.value)
            kwargs = {self.es_field(): self.value}
            s = s.filter("term", **kwargs)
        return s

    def validate(self, query):
        try:
            int(query)
        except ValueError:
            raise APIQueryParamsError(f"Value for param {self.param} must be a number.")


class TermField(Field):
    def build_query(self, s):
        if self.value == "null":
            field_name = self.es_field()
            field_name = field_name.replace("__", ".")
            s = s.exclude("exists", field=field_name)
        elif self.value == "!null":
            field_name = self.es_field()
            field_name = field_name.replace("__", ".")
            s = s.filter("exists", field=field_name)
        elif self.value.startswith("!"):
            query = self.value[1:]
            kwargs = {self.es_field(): query}
            s = s.exclude("term", **kwargs)
        else:
            kwargs = {self.es_field(): self.value}
            s = s.filter("term", **kwargs)
        return s

    def es_field(self) -> str:
        if self.custom_es_field:
            field = self.custom_es_field
        elif "." in self.param:
            field = self.param.replace(".", "__") + "__lower"
        else:
            field = self.param + "__lower"
        return field


class SearchField(Field):
    def build_query(self, s):
        s = search_records(self.value, s)
        return s
