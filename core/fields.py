import datetime
import re
from abc import ABC, abstractmethod

from elasticsearch_dsl import Q, Search

import countries
from core.exceptions import APIQueryParamsError
from core.search import SearchOpenAlex
from core.utils import get_full_openalex_id, normalize_openalex_id
from settings import CONTINENT_PARAMS, EXTERNAL_ID_FIELDS, WORKS_INDEX


class Field(ABC):
    def __init__(self, param, alias=None, custom_es_field=None, nested=False):
        self.param = param
        self.alias = alias
        self.custom_es_field = custom_es_field
        self.value = None
        self.nested = nested

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
        q = None
        if self.param in EXTERNAL_ID_FIELDS:
            self.validate_true_false()
            self.handle_external_id_fields()

        if self.param == "has_oa_accepted_or_published_version":
            self.validate_true_false()
            query = (
                Q("term", host_venue__is_oa="true")
                | Q("term", alternate_host_venues__is_oa="true")
            ) & (
                Q("terms", host_venue__version=["acceptedVersion", "publishedVersion"])
                | Q(
                    "terms",
                    alternate_host_venues__version=[
                        "acceptedVersion",
                        "publishedVersion",
                    ],
                )
            )
            if self.value.lower().strip() == "true":
                q = query
            elif self.value.lower().strip() == "false":
                q = ~query
        elif self.param == "has_oa_submitted_version":
            self.validate_true_false()
            query = (
                Q("term", host_venue__is_oa="true")
                | Q("term", alternate_host_venues__is_oa="true")
            ) & (
                Q("term", host_venue__version="submittedVersion")
                | Q("term", alternate_host_venues__version="submittedVersion")
            )
            if self.value.lower().strip() == "true":
                q = query
            elif self.value.lower().strip() == "false":
                q = ~query
        elif (
            self.param == "has_abstract"
            or self.param == "has_fulltext"
            or self.param == "has_ngrams"
            or self.param == "has_references"
        ):
            self.validate_true_false()
            if self.value.lower().strip() == "true":
                q = Q("exists", field=self.es_field())
            elif self.value.lower().strip() == "false":
                q = ~Q("exists", field=self.es_field())
        elif "is_global_south" in self.param:
            self.validate_true_false()
            country_codes = [
                c["country_code"] for c in countries.GLOBAL_SOUTH_COUNTRIES
            ]
            if self.value.lower().strip() == "true":
                if self.nested:
                    q = Q(
                        "nested",
                        path="authorships",
                        query=Q("terms", **{self.es_field(): country_codes}),
                    )
                else:
                    q = Q("terms", **{self.es_field(): country_codes})
            elif self.value.lower().strip() == "false":
                if self.nested:
                    q = ~Q(
                        "nested",
                        path="authorships",
                        query=Q("terms", **{self.es_field(): country_codes}),
                    )
                else:
                    q = ~Q("terms", **{self.es_field(): country_codes})
            return q
        elif self.value == "null":
            q = ~Q("exists", field=self.es_field())
        elif self.value == "!null":
            q = Q("exists", field=self.es_field())
        else:
            self.validate(self.value)
            kwargs = {self.es_field(): self.value.lower().strip()}
            q = Q("term", **kwargs)
        if q and self.nested:
            q = Q("nested", path="authorships", query=q)
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
        if not normalize_openalex_id(self.value):
            error_id = f"'{self.value.replace('https://openalex.org/', '')}'"
            raise APIQueryParamsError(f"{error_id} is not a valid OpenAlex ID.")
        if self.value == "null":
            field_name = self.es_field()
            field_name = field_name.replace("__", ".")
            if self.nested:
                q = ~Q(
                    "nested", path="authorships", query=Q("exists", field=field_name)
                )
            else:
                q = ~Q("exists", field=field_name)
            return q
        elif self.value == "!null":
            field_name = self.es_field()
            field_name = field_name.replace("__", ".")
            q = Q("exists", field=field_name)
        elif self.value.startswith("!") and "https://openalex.org/" in self.value:
            query = self.value[1:]
            kwargs = {self.es_field(): query}
            if self.nested:
                q = ~Q("nested", path="authorships", query=Q("term", **kwargs))
            else:
                q = ~Q("term", **kwargs)
            return q
        elif self.value.startswith("!"):
            query = self.value[1:].upper()
            query_with_url = f"https://openalex.org/{query}"
            kwargs = {self.es_field(): query_with_url}
            if self.nested:
                q = ~Q("nested", path="authorships", query=Q("term", **kwargs))
            else:
                q = ~Q("term", **kwargs)
        elif self.param == "cited_by":
            openalex_ids = self.get_ids(self.value, "referenced_works")
            q = Q("terms", id=openalex_ids)
        elif self.param == "related_to":
            openalex_ids = self.get_ids(self.value, "related_works")
            q = Q("terms", id=openalex_ids)
        elif "https://openalex.org/" in self.value:
            kwargs = {self.es_field(): self.value}
            q = Q("term", **kwargs)
        else:
            query = f"https://openalex.org/{self.value.upper()}"
            kwargs = {self.es_field(): query}
            q = Q("term", **kwargs)
        if q and self.nested:
            q = Q("nested", path="authorships", query=q)
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
        elif self.value.startswith("-"):
            query = self.value[1:]
            self.validate(query)
            kwargs = {self.es_field(): {"lte": int(query)}}
            q = Q("range", **kwargs)
        elif ">" in self.value:
            query = self.value[1:]
            self.validate(query)
            kwargs = {self.es_field(): {"gt": int(query)}}
            q = Q("range", **kwargs)
        elif self.value.endswith("-"):
            query = self.value[:-1]
            self.validate(query)
            kwargs = {self.es_field(): {"gte": int(query)}}
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
        if (
            self.param == "raw_affiliation_string.search"
            or self.param == "abstract.search"
            or self.param == "fulltext.search"
        ):
            search_oa = SearchOpenAlex(
                search_terms=self.value, primary_field=self.es_field()
            )
            q = search_oa.build_query()
        else:
            search_oa = SearchOpenAlex(search_terms=self.value)
            q = search_oa.build_query()
        return q


class TermField(Field):
    def build_query(self):
        id_params = [
            "author.orcid",
            "authorships.author.orcid",
            "authorships.institutions.ror",
            "doi",
            "ids.pmid",
            "ids.pmcid",
            "institutions.ror",
            "issn",
            "orcid",
            "openalex_id",
            "pmid",
            "pmcid",
            "ror",
            "wikidata_id",
        ]

        if self.value == "null":
            field_name = self.es_field()
            field_name = field_name.replace("__", ".")
            if self.nested:
                q = ~Q(
                    "nested", path="authorships", query=Q("exists", field=field_name)
                )
            else:
                q = ~Q("exists", field=field_name)
            return q
        elif self.value == "!null":
            field_name = self.es_field()
            field_name = field_name.replace("__", ".")
            q = Q("exists", field=field_name)
        elif self.param in id_params:
            formatted_id = self.format_id()
            if formatted_id is None:
                raise APIQueryParamsError(
                    f"{self.value} is not a valid ID for {self.param}"
                )
            kwargs = {self.es_field(): formatted_id}
            q = Q("term", **kwargs)
        elif self.param == "doi_starts_with":
            if "https://doi.org" in self.value:
                raise APIQueryParamsError("Enter DOI in short format such as 10.12")
            if len(self.value) < 3:
                raise APIQueryParamsError(
                    "Enter more than 3 characters to use this filter. Such as 10.12"
                )
            query = f"https://doi.org/{self.value}"
            kwargs = {self.es_field(): query}
            q = Q("prefix", **kwargs)
        elif self.value.startswith("!"):
            query = self.value[1:]
            kwargs = {self.es_field(): query}
            if self.nested:
                q = ~Q("nested", path="authorships", query=Q("term", **kwargs))
            else:
                q = ~Q("term", **kwargs)
            return q
        elif self.param == "display_name":
            kwargs = {self.es_field(): self.value}
            q = Q("match", **kwargs)
        elif self.param == "host_venue.license":
            kwargs = {self.es_field(): self.value.lower()}
            q = Q("term", **kwargs)
        elif "continent" in self.param:
            country_codes = self.get_country_codes()
            kwargs = {self.es_field(): country_codes}
            q = Q("terms", **kwargs)
        else:
            kwargs = {self.es_field(): self.value}
            q = Q("term", **kwargs)
        if q and self.nested:
            q = Q("nested", path="authorships", query=q)
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

    def format_id(self):
        if self.param == "doi" and "doi.org" not in self.value:
            formatted = f"https://doi.org/{self.value}"
        elif (
            self.param == "pmid" or self.param == "ids.pmid"
        ) and "pubmed.ncbi.nlm.nih.gov" not in self.value:
            formatted = f"https://pubmed.ncbi.nlm.nih.gov/{self.value}"
        elif (
            self.param == "pmcid" or self.param == "ids.pmcid"
        ) and "ncbi.nlm.nih.gov/pmc/articles" not in self.value:
            formatted = f"https://www.ncbi.nlm.nih.gov/pmc/articles/{self.value}"
        elif (
            self.param in ["author.orcid", "authorships.author.orcid", "orcid"]
            and "orcid.org" not in self.value
        ):
            formatted = f"https://orcid.org/{self.value}"
        elif self.param == "openalex_id":
            formatted = get_full_openalex_id(self.value)
        elif (
            self.param in ["authorships.institutions.ror", "institutions.ror", "ror"]
            and "ror.org" not in self.value
        ):
            formatted = f"https://ror.org/{self.value}"
        elif self.param == "wikidata_id" and "wikidata.org" not in self.value:
            formatted = f"https://www.wikidata.org/wiki/{self.value}"
        else:
            formatted = self.value
        return formatted

    def get_country_codes(self):
        continent = self.value.lower().strip()
        if (
            self.value.lower() not in CONTINENT_PARAMS.keys()
            and self.value.upper() not in CONTINENT_PARAMS.values()
        ):
            params = list(CONTINENT_PARAMS.keys()) + list(CONTINENT_PARAMS.values())
            raise APIQueryParamsError(
                f"Value for {self.param} must be one of {', '.join(params)}."
            )
        if continent == "africa" or continent.upper() == CONTINENT_PARAMS["africa"]:
            country_codes = [
                c["country_code"] for c in countries.COUNTRIES_BY_CONTINENT["Africa"]
            ]
        elif (
            continent == "antarctica"
            or continent.upper() == CONTINENT_PARAMS["antarctica"]
        ):
            country_codes = [
                c["country_code"]
                for c in countries.COUNTRIES_BY_CONTINENT["Antarctica"]
            ]
        elif continent == "asia" or continent.upper() == CONTINENT_PARAMS["asia"]:
            country_codes = [
                c["country_code"] for c in countries.COUNTRIES_BY_CONTINENT["Asia"]
            ]
        elif continent == "europe" or continent.upper() == CONTINENT_PARAMS["europe"]:
            country_codes = [
                c["country_code"] for c in countries.COUNTRIES_BY_CONTINENT["Europe"]
            ]
        elif (
            continent == "north_america"
            or continent.upper() == CONTINENT_PARAMS["north_america"]
        ):
            country_codes = [
                c["country_code"]
                for c in countries.COUNTRIES_BY_CONTINENT["North America"]
            ]
        elif continent == "oceania" or continent.upper() == CONTINENT_PARAMS["oceania"]:
            country_codes = [
                c["country_code"] for c in countries.COUNTRIES_BY_CONTINENT["Oceania"]
            ]
        elif (
            continent == "south_america"
            or continent.upper() == CONTINENT_PARAMS["south_america"]
        ):
            country_codes = [
                c["country_code"]
                for c in countries.COUNTRIES_BY_CONTINENT["South America"]
            ]
        else:
            country_codes = []
        return country_codes
