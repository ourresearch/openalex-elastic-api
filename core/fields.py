import datetime
import re
from abc import ABC, abstractmethod

from elasticsearch_dsl import Q, Search

import countries
from core.exceptions import APIQueryParamsError
from core.search import SearchOpenAlex
from core.utils import get_full_openalex_id, normalize_openalex_id
from settings import (CONTINENT_PARAMS, EXTERNAL_ID_FIELDS, VERSIONS,
                      WORKS_INDEX)


class Field(ABC):
    def __init__(self, param, alias=None, custom_es_field=None, unique_id=None):
        self.param = param
        self.alias = alias
        self.custom_es_field = custom_es_field
        self.value = None
        self.unique_id = unique_id

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
            or self.param == "primary_location.source.has_issn"
            or self.param == "primary_location.venue.has_issn"
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
                q = Q("terms", **{self.es_field(): country_codes})
            elif self.value.lower().strip() == "false":
                q = ~Q("terms", **{self.es_field(): country_codes})
            return q
        elif self.value == "null":
            q = ~Q("exists", field=self.es_sort_field())
        elif self.value == "!null":
            q = Q("exists", field=self.es_sort_field())
        else:
            self.validate(self.value)
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
        if self.value == "null" and self.param != "repository":
            field_name = self.es_field()
            field_name = field_name.replace("__", ".")
            q = ~Q("exists", field=field_name)
            return q
        elif self.value == "!null" and self.param != "repository":
            field_name = self.es_field()
            field_name = field_name.replace("__", ".")
            q = Q("exists", field=field_name)
            return q
        elif self.value.startswith("!") and self.value != "!null":
            self.validate(self.value[1:])
            query = get_full_openalex_id(self.value[1:])
            kwargs = {self.es_field(): query}
            if self.param == "repository":
                q = ~Q("term", locations__source__id=query)
            else:
                q = ~Q("term", **kwargs)
            return q
        elif self.param == "cited_by":
            openalex_ids = self.get_ids(self.value, "referenced_works")
            q = Q("terms", id=openalex_ids)
        elif self.param == "related_to":
            openalex_ids = self.get_ids(self.value, "related_works")
            q = Q("terms", id=openalex_ids)
        elif self.param == "repository":
            if self.value == "null":
                q = ~Q("exists", field=self.custom_es_field) & Q(
                    "term", **{"locations.source.type": "repository"}
                )
            elif self.value == "!null":
                q = Q("exists", field=self.custom_es_field) & Q(
                    "term", **{"locations.source.type": "repository"}
                )
            else:
                self.validate(self.value)
                kwargs = {self.custom_es_field: get_full_openalex_id(self.value)}
                q = Q("term", **kwargs) & Q(
                    "term", **{"locations.source.type": "repository"}
                )
        else:
            self.validate(self.value)
            query = get_full_openalex_id(self.value)
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

    def validate(self, query):
        if not normalize_openalex_id(query):
            error_id = f"'{self.value.replace('https://openalex.org/', '')}'"
            raise APIQueryParamsError(f"{error_id} is not a valid OpenAlex ID.")

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
            kwargs = {self.es_field(): {"lt": float(query)}}
            q = Q("range", **kwargs)
        elif self.value.startswith("-"):
            query = self.value[1:]
            self.validate(query)
            kwargs = {self.es_field(): {"lte": float(query)}}
            q = Q("range", **kwargs)
        elif ">" in self.value:
            query = self.value[1:]
            self.validate(query)
            kwargs = {self.es_field(): {"gt": float(query)}}
            q = Q("range", **kwargs)
        elif self.value.endswith("-"):
            query = self.value[:-1]
            self.validate(query)
            kwargs = {self.es_field(): {"gte": float(query)}}
            q = Q("range", **kwargs)
        elif "-" in self.value:
            values = self.value.strip().split("-")
            left_value = values[0]
            right_value = values[1]
            self.validate(left_value)
            self.validate(right_value)
            kwargs = {
                self.es_field(): {"gte": float(left_value), "lte": float(right_value)}
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
            float(query)
        except ValueError:
            raise APIQueryParamsError(f"Value for param {self.param} must be a number.")


class SearchField(Field):
    def build_query(self):
        self.validate(self.value)
        if (
            self.param == "raw_affiliation_string.search"
            or self.param == "abstract.search"
            or self.param == "fulltext.search"
        ):
            search_oa = SearchOpenAlex(
                search_terms=self.value, primary_field=self.es_field()
            )
            q = search_oa.build_query()
        elif self.param == "display_name.search" and self.unique_id == "author_search":
            search_oa = SearchOpenAlex(
                search_terms=self.value,
                is_author_name_query=True,
            )
            q = search_oa.build_query()
        else:
            search_oa = SearchOpenAlex(search_terms=self.value)
            q = search_oa.build_query()
        return q

    def validate(self, query):
        if any([word.startswith("!") for word in query.split()]):
            raise APIQueryParamsError(
                f"Search filters do not support the ! operator. Problem value: {query}"
            )


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
            if self.param == "version":
                q = ~Q("exists", field="host_venue.version") & ~Q(
                    "exists", field="alternate_host_venues.version"
                )
            else:
                q = ~Q("exists", field=field_name)
            return q
        elif self.value == "!null":
            if self.param == "version":
                q = Q("exists", field="host_venue.version") | Q(
                    "exists", field="alternate_host_venues.version"
                )
            else:
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
            if "continent" in self.param:
                country_codes = self.get_country_codes()
                q = ~Q("terms", **{self.es_field(): country_codes})
            elif self.param == "version":
                version = self.validate_version()
                kwargs1 = {"host_venue.version": version}
                kwargs2 = {"alternate_host_venues.version": version}
                q = ~(Q("term", **kwargs1) | Q("term", **kwargs2))
            elif self.param == "host_venue.version":
                version = self.validate_version()
                kwargs = {"host_venue.version": version}
                q = ~Q("term", **kwargs)
            else:
                q = ~Q("term", **kwargs)
            return q
        elif self.param == "apc_prices.currency":
            kwargs = {self.es_field(): self.value.upper()}
            q = Q("term", **kwargs)
        elif self.param == "display_name":
            kwargs = {self.es_field(): self.value}
            q = Q("match", **kwargs)
        elif self.param == "host_venue.license":
            kwargs = {self.es_field(): self.value.lower()}
            q = Q("term", **kwargs)
        elif self.param == "host_venue.version":
            version = self.validate_version()
            kwargs = {self.es_field(): version}
            q = Q("term", **kwargs)
        elif "continent" in self.param:
            country_codes = self.get_country_codes()
            kwargs = {self.es_field(): country_codes}
            q = Q("terms", **kwargs)
        elif self.param == "version":
            version = self.validate_version()
            kwargs1 = {"host_venue.version": version}
            kwargs2 = {"alternate_host_venues.version": version}
            q = Q("term", **kwargs1) | Q("term", **kwargs2)
        elif self.param == "best_open_version":
            self.validate_best_open_version()
            submitted_query = Q("term", **{self.custom_es_field: "submittedVersion"})
            accepted_query = Q("term", **{self.custom_es_field: "acceptedVersion"})
            published_query = Q("term", **{self.custom_es_field: "publishedVersion"})
            if self.value.lower() == "any":
                q = submitted_query | accepted_query | published_query
            elif self.value.lower() == "acceptedorpublished":
                q = accepted_query | published_query
            elif self.value.lower() == "published":
                q = published_query
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
            if self.unique_id and self.unique_id == "wikidata_entity":
                formatted = f"https://www.wikidata.org/entity/{self.value}"
            else:
                formatted = f"https://www.wikidata.org/wiki/{self.value}"
        else:
            formatted = self.value
        return formatted

    def get_country_codes(self):
        if self.value.startswith("!"):
            continent = self.value[1:].lower().strip()
        else:
            continent = self.value.lower().strip()
        if (
            continent not in CONTINENT_PARAMS.keys()
            and continent.upper() not in CONTINENT_PARAMS.values()
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

    def validate_version(self):
        if self.value.startswith("!"):
            value = self.value[1:]
        else:
            value = self.value
        lower_case_versions = [v.lower() for v in VERSIONS]
        if value.lower() not in lower_case_versions:
            raise APIQueryParamsError(
                f"Value for {self.param} must be one of {', '.join(VERSIONS)}."
            )
        if value.lower() == "null":
            version = "null"
        elif value.lower() == "submittedversion":
            version = "submittedVersion"
        elif value.lower() == "acceptedversion":
            version = "acceptedVersion"
        elif value.lower() == "publishedversion":
            version = "publishedVersion"
        else:
            version = value
        return version

    def validate_best_open_version(self):
        valid_values = ["any", "acceptedOrPublished", "published"]
        if self.value.lower() not in [value.lower() for value in valid_values]:
            raise APIQueryParamsError(
                f"Value for {self.param} must be one of {', '.join(valid_values)} and not {self.value}."
            )
