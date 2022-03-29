import datetime
import re
from abc import ABC, abstractmethod

from elasticsearch_dsl import Q, Search

import settings
from core.exceptions import APIQueryParamsError
from core.search import (search_records_experiment, search_records_full,
                         search_records_phrase)
from core.utils import get_full_openalex_id
from settings import EXTERNAL_ID_FIELDS, WORKS_INDEX


class Field(ABC):
    def __init__(self, param, alias=None, custom_es_field=None):
        self.param = param
        self.alias = alias
        self.custom_es_field = custom_es_field
        self.value = None

    @abstractmethod
    def build_query(self):
        pass

    def validate(self, query):
        pass

    def es_field(self) -> str:
        if self.custom_es_field:
            field = self.custom_es_field
        elif self.alias:
            field = self.alias.replace(".", "__")
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
    def build_query(self):
        if self.param in settings.EXTERNAL_ID_FIELDS:
            self.validate_true_false()
            self.handle_external_id_fields()
        else:
            self.validate(self.value)
        if self.value == "null":
            q = ~Q("exists", field=self.es_field())
        elif self.value == "!null":
            q = Q("exists", field=self.es_field())
        else:
            kwargs = {self.es_field(): self.value.lower().strip()}
            q = Q("term", **kwargs)
        return q

    def validate(self, query):
        valid_values = ["null", "!null", "true", "false"]
        query = query.lower().strip()
        if query not in valid_values:
            raise APIQueryParamsError(
                f"Value for {self.param} must be true, false null, or !null: not {query}."
            )

    def handle_external_id_fields(self):
        if self.value.lower().strip() == "true":
            self.value = "!null"
        elif self.value.lower().strip() == "false":
            self.value = "null"

    def validate_true_false(self):
        valid_values = ["true", "false"]
        query = self.value.lower().strip()
        if query not in valid_values:
            raise APIQueryParamsError(
                f"Value for {self.param} must be true or false, not {query}."
            )


class DateField(Field):
    def build_query(self):
        if "<" in self.value:
            query = self.value[1:]
            self.validate(query)
            kwargs = {self.es_field(): {"lt": query}}
            q = Q("range", **kwargs)
        elif ">" in self.value:
            query = self.value[1:]
            self.validate(query)
            kwargs = {self.es_field(): {"gt": query}}
            q = Q("range", **kwargs)
        elif self.param == "to_publication_date":
            self.validate(self.value)
            kwargs = {self.es_field(): {"lte": self.value}}
            q = Q("range", **kwargs)
        elif (
            self.param == "from_publication_date"
            or self.param == "from_created_date"
            or self.param == "from_updated_date"
        ):
            self.validate(self.value)
            kwargs = {self.es_field(): {"gte": self.value}}
            q = Q("range", **kwargs)
        elif self.value == "null":
            q = ~Q("exists", field=self.es_field())
        else:
            self.validate(self.value)
            kwargs = {self.es_field(): self.value}
            q = Q("term", **kwargs)
        return q

    def validate(self, query):
        date = re.search("\d{4}-\d{2}-\d{2}", query)
        invalid_date_message = f"Value for param {self.param} is an invalid date. Format is yyyy-mm-dd (e.g. 2020-05-17)."
        if not date:
            raise APIQueryParamsError(invalid_date_message)
        try:
            datetime.datetime.strptime(query, "%Y-%m-%d")
        except ValueError:
            raise APIQueryParamsError(invalid_date_message)


class OpenAlexIDField(Field):
    def build_query(self):
        if self.value == "null":
            field_name = self.es_field()
            field_name = field_name.replace("__", ".")
            q = ~Q("exists", field=field_name)
        elif self.value == "!null":
            field_name = self.es_field()
            field_name = field_name.replace("__", ".")
            q = Q("exists", field=field_name)
        elif self.value.startswith("!") and "https://openalex.org/" in self.value:
            query = self.value[1:]
            kwargs = {self.es_field(): query}
            q = ~Q("term", **kwargs)
        elif self.value.startswith("!"):
            query = self.value[1:].upper()
            query_with_url = f"https://openalex.org/{query}"
            kwargs = {self.es_field(): query_with_url}
            q = ~Q("term", **kwargs)
        elif self.param == "cited_by":
            openalex_ids = self.get_ids(self.value, "referenced_works")
            q = Q("terms", id=openalex_ids)
            return q
        elif self.param == "related_to":
            openalex_ids = self.get_ids(self.value, "related_works")
            q = Q("terms", id=openalex_ids)
            return q
        elif "https://openalex.org/" in self.value:
            kwargs = {self.es_field(): self.value}
            q = Q("term", **kwargs)
        else:
            query = f"https://openalex.org/{self.value.upper()}"
            kwargs = {self.es_field(): query}
            q = Q("term", **kwargs)
        return q

    def es_field(self) -> str:
        if self.custom_es_field:
            field = self.custom_es_field
        elif self.alias:
            field = self.alias.replace(".", "__") + "__lower"
        elif "." in self.param:
            field = self.param.replace(".", "__") + "__lower"
        else:
            field = self.param + "__lower"
        return field

    @staticmethod
    def get_ids(openalex_id, category):
        full_openalex_id = get_full_openalex_id(openalex_id)
        if not full_openalex_id:
            raise APIQueryParamsError(
                "Invalid OpenAlex ID in cited_by or related_to filter."
            )
        openalex_ids = []
        s = Search(index=WORKS_INDEX).extra(size=1)
        s = s.filter("term", id=full_openalex_id)
        response = s.execute()
        if response:
            for h in response:
                openalex_ids = [id for id in h[category]]
        return openalex_ids


class PhraseField(Field):
    def build_query(self):
        if self.value == "null":
            field_name = self.es_field()
            field_name = field_name.replace("__", ".")
            q = ~Q("exists", field=field_name)
        elif self.value == "!null":
            field_name = self.es_field()
            field_name = field_name.replace("__", ".")
            q = Q("exists", field=field_name)
        elif self.value.startswith("!"):
            query = self.value[1:]
            kwargs = {self.es_field(): query}
            q = ~Q("match_phrase", **kwargs)
        else:
            kwargs = {self.es_field(): self.value}
            q = Q("match_phrase", **kwargs)
        return q

    def es_field(self) -> str:
        if self.custom_es_field:
            field = self.custom_es_field
        elif self.alias:
            field = self.alias.replace(".", "__") + "__lower"
        elif "." in self.param:
            field = self.param.replace(".", "__") + "__lower"
        else:
            field = self.param + "__lower"
        return field


class RangeField(Field):
    def build_query(self):
        if "<" in self.value:
            query = self.value[1:]
            self.validate(query)
            kwargs = {self.es_field(): {"lt": int(query)}}
            q = Q("range", **kwargs)
        elif ">" in self.value:
            query = self.value[1:]
            self.validate(query)
            kwargs = {self.es_field(): {"gt": int(query)}}
            q = Q("range", **kwargs)
        elif "-" in self.value:
            values = self.value.strip().split("-")
            left_value = values[0]
            right_value = values[1]
            self.validate(left_value)
            self.validate(right_value)
            kwargs = {
                self.es_field(): {"gte": int(left_value), "lte": int(right_value)}
            }
            q = Q("range", **kwargs)
        elif self.value == "null":
            q = ~Q("exists", field=self.es_field())
        else:
            self.validate(self.value)
            kwargs = {self.es_field(): self.value}
            q = Q("term", **kwargs)
        return q

    def validate(self, query):
        try:
            int(query)
        except ValueError:
            raise APIQueryParamsError(f"Value for param {self.param} must be a number.")


class SearchField(Field):
    def build_query(self):
        if self.value.startswith('"') and self.value.endswith('"'):
            q = search_records_phrase(self.value)
        elif self.value.startswith("[") and self.value.endswith("]"):
            q = search_records_experiment(self.value)
        else:
            q = search_records_full(self.value)
        return q


class TermField(Field):
    def build_query(self):
        if self.value == "null":
            field_name = self.es_field()
            field_name = field_name.replace("__", ".")
            q = ~Q("exists", field=field_name)
        elif self.value == "!null":
            field_name = self.es_field()
            field_name = field_name.replace("__", ".")
            q = Q("exists", field=field_name)
        elif self.value.startswith("!"):
            query = self.value[1:]
            kwargs = {self.es_field(): query}
            q = ~Q("term", **kwargs)
        else:
            kwargs = {self.es_field(): self.value}
            q = Q("term", **kwargs)
        return q

    def es_field(self) -> str:
        if self.custom_es_field:
            field = self.custom_es_field
        elif self.alias:
            field = self.alias.replace(".", "__") + "__lower"
        elif "." in self.param:
            field = self.param.replace(".", "__") + "__lower"
        else:
            field = self.param + "__lower"
        return field
