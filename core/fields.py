import datetime
import re
from abc import ABC, abstractmethod

from elasticsearch_dsl import Q, Search

import country_list
from core.exceptions import APIQueryParamsError
from core.search import SearchOpenAlex, full_search_query
from core.utils import get_full_openalex_id, normalize_openalex_id
from settings import CONTINENT_PARAMS, EXTERNAL_ID_FIELDS, VERSIONS, WORKS_INDEX


class Field(ABC):
    def __init__(
        self,
        param,
        alias=None,
        custom_es_field=None,
        unique_id=None,
        index=None,
        docstring="",
        documentation_link="",
        alternate_names=None,
    ):
        self.param = param
        self.alias = alias
        self.custom_es_field = custom_es_field
        self.value = None
        self.unique_id = unique_id
        self.index = index
        self.docstring = docstring
        self.documentation_link = documentation_link
        self.alternate_names = (
            alternate_names  # optional list of strings, useful for search
        )

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
            query = Q("term", locations__is_oa="true") & Q(
                "terms", locations__version=["acceptedVersion", "publishedVersion"]
            )
            if self.value.lower().strip() == "true":
                q = query
            elif self.value.lower().strip() == "false":
                q = ~query
        elif self.param == "has_oa_submitted_version":
            self.validate_true_false()
            query = Q("term", locations__is_oa="true") & Q(
                "term", locations__version="submittedVersion"
            )
            if self.value.lower().strip() == "true":
                q = query
            elif self.value.lower().strip() == "false":
                q = ~query
        elif (
            self.param == "has_abstract"
            or self.param == "has_embeddings"
            or self.param == "has_pdf_url"
            or self.param == "has_raw_affiliation_strings"
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
                c["country_code"] for c in country_list.GLOBAL_SOUTH_COUNTRIES
            ]
            if self.value.lower().strip() == "true":
                q = Q("terms", **{self.es_field(): country_codes})
            elif self.value.lower().strip() == "false":
                q = ~Q("terms", **{self.es_field(): country_codes})
            return q
        elif self.param == "has_old_authors":
            q = (
                Q("prefix", authorships__author__id="https://openalex.org/A4")
                | Q("prefix", authorships__author__id="https://openalex.org/A3")
                | Q("prefix", authorships__author__id="https://openalex.org/A2")
                | Q("prefix", authorships__author__id="https://openalex.org/A1")
            )
        elif self.param == "mag_only":
            self.validate_true_false()
            if self.value.lower().strip() == "true":
                q = (
                    Q("exists", field="ids.mag")
                    & ~Q("exists", field="ids.pmid")
                    & ~Q("exists", field="ids.pmcid")
                    & ~Q("exists", field="ids.doi")
                    & ~Q("exists", field="ids.arxiv")
                )
            else:
                q = (
                    Q("exists", field="ids.pmid")
                    | Q("exists", field="ids.pmcid")
                    | Q("exists", field="ids.doi")
                    | Q("exists", field="ids.arxiv")
                )
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
        elif self.param == "to_publication_date" or self.param == "to_updated_date" or self.param == "to_created_date":
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


class DateTimeField(DateField):
    def validate(self, query):
        # override DateField.validate()

        # First check to make sure it starts with a valid date string
        date = re.search("\d{4}-\d{2}-\d{2}", query)

        invalid_date_message = f'Value for param {self.param} is an invalid date. The date must be in ISO-8601 format, for example: "2020-05-17", "2020-05-17T15:30", or "2020-01-02T00:22:35.180390". (Value given was {query})'
        if not date:
            raise APIQueryParamsError(invalid_date_message)
        try:
            datetime.datetime.fromisoformat(query.replace("Z", "+00:00"))
        except ValueError:
            raise APIQueryParamsError(invalid_date_message)


class OpenAlexIDField(Field):
    def build_query(self):
        if self.param == "authorships.institutions.id":
            if self.value == "null":
                q = ~Q("exists", field="authorships.institutions.id") & ~Q("exists", field="institution_assertions.id")
            elif self.value == "!null":
                q = Q("exists", field="authorships.institutions.id") & Q("exists", field="institution_assertions.id")
            elif self.value.startswith("!"):
                query = self.value[1:]
                query = get_full_openalex_id(query)
                self.validate(self.value)
                q = ~Q("term", **{"authorships.institutions.id": query}) & ~Q("term", **{"institution_assertions.id": query})
            else:
                query = get_full_openalex_id(self.value)
                self.validate(self.value)
                q = Q("term", **{"authorships.institutions.id": query}) | Q("term", **{"institution_assertions.id": query})
            return q
        elif self.param == "authorships.institutions.lineage":
            if self.value == "null":
                q = ~Q("exists", field="authorships.institutions.lineage") & ~Q("exists", field="institution_assertions.lineage")
            elif self.value == "!null":
                q = Q("exists", field="authorships.institutions.lineage") & Q("exists", field="institution_assertions.lineage")
            elif self.value.startswith("!"):
                query = self.value[1:]
                query = get_full_openalex_id(query)
                self.validate(self.value)
                q = ~Q("term", **{"authorships.institutions.lineage": query}) & ~Q("term", **{"institution_assertions.lineage": query})
            else:
                query = get_full_openalex_id(self.value)
                self.validate(self.value)
                q = Q("term", **{"authorships.institutions.lineage": query}) | Q("term", **{"institution_assertions.lineage": query})
            return q
        elif self.value == "null" and self.param not in ["repository", "journal"]:
            field_name = self.es_field()
            field_name = field_name.replace("__", ".")
            q = ~Q("exists", field=field_name)
            return q
        elif self.value == "!null" and self.param not in ["repository", "journal"]:
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
            elif self.param == "journal":
                q = ~Q("term", primary_location__source__id=query)
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
        elif self.param == "journal":
            if self.value == "null":
                q = ~Q("exists", field=self.custom_es_field) & Q(
                    "term", **{"primary_location.source.type": "journal"}
                )
            elif self.value == "!null":
                q = Q("exists", field=self.custom_es_field) & Q(
                    "term", **{"primary_location.source.type": "journal"}
                )
            else:
                self.validate(self.value)
                kwargs = {self.custom_es_field: get_full_openalex_id(self.value)}
                q = Q("term", **kwargs) & Q(
                    "term", **{"primary_location.source.type": "journal"}
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

        if (
            self.param == "locations.source.host_institution_lineage"
            and not normalize_openalex_id(query).startswith("I")
        ):
            raise APIQueryParamsError(
                "Use an institution ID with this convenience filter (OpenAlex ID that starts with I)."
            )
        elif (
            self.param == "locations.source.publisher_lineage"
            and not normalize_openalex_id(query).startswith("P")
        ):
            raise APIQueryParamsError(
                "Use a publisher ID with this convenience filter (OpenAlex ID that starts with P)."
            )

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
        elif self.value.startswith("!"):
            if "-" in self.value:
                values = self.value[1:].strip().split("-")
                left_value = values[0]
                right_value = values[1]
                self.validate(left_value)
                self.validate(right_value)
                kwargs = {
                    self.es_field(): {
                        "gte": float(left_value),
                        "lte": float(right_value),
                    }
                }
                q = ~Q("range", **kwargs)
            else:
                query = self.value[1:]
                kwargs = {self.es_field(): float(query)}
                q = ~Q("term", **kwargs)
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
        if self.param == "default.search":
            q = full_search_query(self.index, self.value)
        elif (
            self.param == "raw_affiliation_strings.search"
            or self.param == "abstract.search"
            or self.param == "abstract.search.no_stem"
            or self.param == "fulltext.search"
            or self.param == "keyword.search"
            or self.param == "description.search"
            or self.param == "title.search"
            or self.param == "title.search.no_stem"
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
        elif self.param == "display_name.search.no_stem":
            search_oa = SearchOpenAlex(
                search_terms=self.value,
                primary_field=self.es_field(),
            )
            q = search_oa.build_query()
        elif self.param == "raw_author_name.search":
            search_oa = SearchOpenAlex(
                search_terms=self.value,
                primary_field="authorships.raw_author_name",
            )
            q = search_oa.build_query()
        elif self.param == "title_and_abstract.search":
            search_oa = SearchOpenAlex(
                search_terms=self.value,
                primary_field="display_name",
                secondary_field="abstract",
            )
            q = search_oa.build_query()
        elif self.param == "title_and_abstract.search.no_stem":
            search_oa = SearchOpenAlex(
                search_terms=self.value,
                primary_field="display_name.nostem",
                secondary_field="abstract.nostem",
            )
            q = search_oa.build_query()
        elif self.param == "semantic.search":
            search_oa = SearchOpenAlex(
                search_terms=self.value,
                is_semantic_query=True,
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
    def build_terms_query(self, values):
        """
        Build an Elasticsearch terms query (plural) for multiple values.
        More efficient than multiple bool/should queries.
        """
        # Format all values according to the field type
        formatted_values = []
        for val in values:
            self.value = val
            formatted_val = self._get_formatted_value()
            formatted_values.append(formatted_val)

        # For DOI, we need to handle both v1 (full URL) and v2 (short form)
        if self.param == "doi":
            expanded_values = []
            for val in values:
                if "doi.org" in val:
                    short_doi = val.replace("https://doi.org/", "")
                    expanded_values.extend([val, short_doi])
                else:
                    full_doi = f"https://doi.org/{val}"
                    expanded_values.extend([val, full_doi])
            formatted_values = expanded_values

        kwargs = {self.es_field(): formatted_values}
        return Q("terms", **kwargs)

    def _get_formatted_value(self):
        """
        Get the formatted value for a single term, handling all the special cases.
        Returns the value that would be used in the term query.
        """
        id_params = [
            "affiliations.institution.ror",
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

        # Apply the same transformations as in build_query
        if self.param == "sustainable_development_goals.id":
            if len(self.value) == 1 or len(self.value) == 2:
                return f"https://metadata.un.org/sdg/{self.value}"
            elif self.value.startswith("sdgs/"):
                sdg_number = self.value.replace("sdgs/", "")
                return f"https://metadata.un.org/sdg/{sdg_number}"
        elif self.param == "language":
            return self.value.replace("languages/", "")
        elif self.param == "type" or self.param == "last_known_institution.type":
            return (
                self.value.replace("work-types/", "")
                .replace("institution-types/", "")
                .replace("source-types/", "")
                .replace("types/", "")
            )
        elif (
            self.param == "primary_location.source.type"
            or self.param == "locations.source.type"
        ):
            return self.value.replace("source-types/", "").replace("%20", " ")
        elif "country_code" in self.param or "countries" in self.param:
            return self.value.replace("countries/", "")
        elif self.param == "keywords.id":
            return self.value.replace("https://openalex.org/", "").replace(
                "keywords/", ""
            )
        elif (
            self.param
            and self.param.endswith("license_id")
            or self.param.endswith("license")
        ):
            if self.value.startswith("https://openalex.org/licenses/"):
                return self.value
            elif self.value.startswith("licenses/"):
                return f"https://openalex.org/{self.value}"
            else:
                return f"https://openalex.org/licenses/{self.value}"
        elif self.param == "id":
            if "keywords/" in self.value and not self.value.startswith(
                "https://openalex.org/"
            ):
                return f"https://openalex.org/{self.value}"
        elif self.param == "doi":
            if "doi.org" in self.value:
                return self.value
            else:
                return f"https://doi.org/{self.value}"
        elif self.param == "display_name":
            return self.value
        elif self.param == "language":
            return self.value.lower()
        elif self.param == "topics.id" or self.param == "topic_share.id":
            if self.value.startswith("https://openalex.org/"):
                return self.value
            else:
                return f"https://openalex.org/{self.value}"
        elif (
            self.param == "topics.domain.id"
            or self.param == "primary_topic.domain.id"
            or self.param == "domain.id"
        ):
            if self.value.startswith("https://openalex.org/domains/"):
                return self.value
            elif self.value.startswith("domains/"):
                return f"https://openalex.org/{self.value}"
            else:
                return f"https://openalex.org/domains/{self.value}"
        elif (
            self.param == "topics.field.id"
            or self.param == "primary_topic.field.id"
            or self.param == "field.id"
        ):
            if self.value.startswith("https://openalex.org/fields/"):
                return self.value
            elif self.value.startswith("fields/"):
                return f"https://openalex.org/{self.value}"
            else:
                return f"https://openalex.org/fields/{self.value}"
        elif (
            self.param == "topics.subfield.id"
            or self.param == "primary_topic.subfield.id"
            or self.param == "subfield.id"
        ):
            if self.value.startswith("https://openalex.org/subfields/"):
                return self.value
            elif self.value.startswith("subfields/"):
                return f"https://openalex.org/{self.value}"
            else:
                return f"https://openalex.org/subfields/{self.value}"
        elif self.param in id_params:
            formatted_id = self.format_id()
            if formatted_id is None:
                raise APIQueryParamsError(
                    f"{self.value} is not a valid ID for {self.param}"
                )
            return formatted_id

        return self.value

    def build_query(self):
        id_params = [
            "affiliations.institution.ror",
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
        if self.param == "sustainable_development_goals.id":
            if len(self.value) == 1 or len(self.value) == 2:
                self.value = f"https://metadata.un.org/sdg/{self.value}"
            elif self.value.startswith("sdgs/"):
                sdg_number = self.value.replace("sdgs/", "")
                self.value = f"https://metadata.un.org/sdg/{sdg_number}"
        elif self.param == "language":
            self.value = self.value.replace("languages/", "")
        elif self.param == "type" or self.param == "last_known_institution.type":
            self.value = (
                self.value.replace("work-types/", "")
                .replace("institution-types/", "")
                .replace("source-types/", "")
                .replace("types/", "")
            )
        elif (
            self.param == "primary_location.source.type"
            or self.param == "locations.source.type"
        ):
            self.value = self.value.replace("source-types/", "").replace("%20", " ")
        elif "country_code" in self.param or "countries" in self.param:
            self.value = self.value.replace("countries/", "")
        elif "domain" in self.param:
            self.value = self.value.replace("domains/", "")
        elif "field" in self.param and "subfield" not in self.param:
            self.value = self.value.replace("fields/", "")
        elif "subfield" in self.param:
            self.value = self.value.replace("subfields/", "")
        elif self.param == "keywords.id":
            self.value = self.value.replace("https://openalex.org/", "").replace(
                "keywords/", ""
            )
        elif (
            self.param
            and self.param.endswith("license_id")
            or self.param.endswith("license")
        ):
            self.value = self.value.replace("https://openalex.org/", "").replace(
                "licenses/", ""
            )
        elif self.param == "authorships.institutions.country_code":
            self.value = self.value.replace("countries/", "")
            if self.value == "null":
                q = ~Q("exists", field="authorships.institutions.country_code") & ~Q(
                    "exists", field="institution_assertions.country_code"
                )
            elif self.value == "!null":
                q = Q("exists", field="authorships.institutions.country_code") & Q(
                    "exists", field="institution_assertions.country_code"
                )
            elif self.value.startswith("!"):
                query = self.value[1:]
                q = ~Q("term", **{"authorships.institutions.country_code": query}) & ~Q(
                    "term", **{"institution_assertions.country_code": query})
            else:
                q = Q("term", **{"authorships.institutions.country_code": self.value}) | Q(
                    "term", **{"institution_assertions.country_code": self.value}
                )
            return q
        elif self.param == "authorships.institutions.ror":
            if self.value == "null":
                q = ~Q("exists", field="authorships.institutions.ror") & ~Q(
                    "exists", field="institution_assertions.ror"
                )
            elif self.value == "!null":
                q = Q("exists", field="authorships.institutions.ror") & Q(
                    "exists", field="institution_assertions.ror"
                )
            elif self.value.startswith("!"):
                query = self.value[1:]
                if "ror.org" not in query:
                    query = f"https://ror.org/{query}"
                q = ~Q("term", **{"authorships.institutions.ror": query}) & ~Q(
                    "term", **{"institution_assertions.ror": query}
                )
            else:
                if "ror.org" not in self.value:
                    self.value = f"https://ror.org/{self.value}"
                q = Q("term", **{"authorships.institutions.ror": self.value}) | Q(
                    "term", **{"institution_assertions.ror": self.value}
                )
            return q
        elif self.param == "authorships.institutions.type":
            self.value = self.value.replace("institution-types/", "")
            if self.value == "null":
                q = ~Q("exists", field="authorships.institutions.type") & ~Q(
                    "exists", field="institution_assertions.type"
                )
            elif self.value == "!null":
                q = Q("exists", field="authorships.institutions.type") & Q(
                    "exists", field="institution_assertions.type"
                )
            elif self.value.startswith("!"):
                query = self.value[1:]
                q = ~Q("term", **{"authorships.institutions.type": query}) & ~Q(
                    "term", **{"institution_assertions.type": query}
                )
            else:
                q = Q("term", **{"authorships.institutions.type": self.value}) | Q(
                    "term", **{"institution_assertions.type": self.value}
                )
        elif self.param == "id":
            if "keywords/" in self.value and not self.value.startswith(
                "https://openalex.org/"
            ):
                self.value = f"https://openalex.org/{self.value}"
        if self.value == "null":
            field_name = self.es_field()
            field_name = field_name.replace("__", ".")
            if self.param == "version":
                q = ~Q("exists", field="locations.version")
            else:
                q = ~Q("exists", field=field_name)
            return q
        elif self.value == "!null":
            if self.param == "version":
                q = Q("exists", field="locations.version")
            else:
                field_name = self.es_field()
                field_name = field_name.replace("__", ".")
                q = Q("exists", field=field_name)
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
        elif self.param == "scopus":
            # a search against the ids.scopus field should give the correct result
            from ids.utils import normalize_scopus

            scopus = normalize_scopus(self.value)
            q = Q("match", **{"ids.scopus": scopus})
        elif self.value.startswith("!"):
            query = self.value[1:]
            if (
                self.param
                in [
                    "affiliations.institution.ror",
                    "authorships.institutions.ror",
                    "institutions.ror",
                    "ror",
                ]
                and "ror.org" not in self.value
            ):
                query = f"https://ror.org/{query}"
            kwargs = {self.es_field(): query}
            if "continent" in self.param:
                country_codes = self.get_country_codes()
                q = ~Q("terms", **{self.es_field(): country_codes})
            elif (
                self.param == "topics.domain.id"
                or self.param == "primary_topic.domain.id"
                or self.param == "domain.id"
            ):
                formatted_version = f"https://openalex.org/domains/{query}"
                kwargs_new_format = {self.es_field(): formatted_version}
                kwargs_old_format = {self.es_field(): query}
                q = ~(Q("term", **kwargs_new_format) | Q("term", **kwargs_old_format))
            elif (
                self.param == "topics.field.id"
                or self.param == "primary_topic.field.id"
                or self.param == "field.id"
            ):
                formatted_version = f"https://openalex.org/fields/{query}"
                kwargs_new_format = {self.es_field(): formatted_version}
                kwargs_old_format = {self.es_field(): query}
                q = ~(Q("term", **kwargs_new_format) | Q("term", **kwargs_old_format))
            elif (
                self.param == "topics.subfield.id"
                or self.param == "primary_topic.subfield.id"
                or self.param == "subfield.id"
            ):
                formatted_version = f"https://openalex.org/subfields/{query}"
                kwargs_new_format = {self.es_field(): formatted_version}
                kwargs_old_format = {self.es_field(): query}
                q = ~(Q("term", **kwargs_new_format) | Q("term", **kwargs_old_format))
            elif self.param == "keywords.id":
                formatted_version = f"https://openalex.org/keywords/{query}"
                kwargs = {self.es_field(): formatted_version}
                q = ~Q("term", **kwargs)
            elif (
                self.param
                and self.param.endswith("license_id")
                or self.param.endswith("license")
            ):
                formatted_version = f"https://openalex.org/licenses/{query}"
                kwargs = {self.es_field(): formatted_version}
                q = ~Q("term", **kwargs)
            else:
                q = ~Q("term", **kwargs)
            return q
        elif self.param == "display_name":
            kwargs = {self.es_field(): self.value}
            q = Q("match", **kwargs)
        elif "continent" in self.param:
            country_codes = self.get_country_codes()
            kwargs = {self.es_field(): country_codes}
            q = Q("terms", **kwargs)
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
        elif self.param == "language":
            kwargs = {self.es_field(): self.value.lower()}
            q = Q("term", **kwargs)
        elif self.param == "topics.id" or self.param == "topic_share.id":
            if "https://openalex.org/" not in self.value:
                formatted_version = f"https://openalex.org/{self.value}"
                kwargs = {self.es_field(): formatted_version}
                q = Q("term", **kwargs)
        elif (
            self.param == "topics.domain.id"
            or self.param == "primary_topic.domain.id"
            or self.param == "domain.id"
        ):
            formatted_version = f"https://openalex.org/domains/{self.value}"
            kwargs_new_format = {self.es_field(): formatted_version}
            kwargs_old_format = {self.es_field(): self.value}
            q = Q("term", **kwargs_new_format) | Q("term", **kwargs_old_format)
        elif (
            self.param == "topics.field.id"
            or self.param == "primary_topic.field.id"
            or self.param == "field.id"
        ):
            formatted_version = f"https://openalex.org/fields/{self.value}"
            kwargs_new_format = {self.es_field(): formatted_version}
            kwargs_old_format = {self.es_field(): self.value}
            q = Q("term", **kwargs_new_format) | Q("term", **kwargs_old_format)
        elif (
            self.param == "topics.subfield.id"
            or self.param == "primary_topic.subfield.id"
            or self.param == "subfield.id"
        ):
            formatted_version = f"https://openalex.org/subfields/{self.value}"
            kwargs_new_format = {self.es_field(): formatted_version}
            kwargs_old_format = {self.es_field(): self.value}
            q = Q("term", **kwargs_new_format) | Q("term", **kwargs_old_format)
        elif self.param == "keywords.id":
            formatted_version = f"https://openalex.org/keywords/{self.value}"
            kwargs = {self.es_field(): formatted_version}
            q = Q("term", **kwargs)
        elif (
            self.param
            and self.param.endswith("license_id")
            or self.param.endswith("license")
        ):
            formatted_version = f"https://openalex.org/licenses/{self.value}"
            kwargs = {self.es_field(): formatted_version}
            q = Q("term", **kwargs)
        elif self.param == "doi":
            # Special handling for DOI to support both data versions:
            # v1: stores full URL like "https://doi.org/10.1590/..."
            # v2: stores short form like "10.1590/..."
            if "doi.org" in self.value:
                # Already a full URL, extract the short form
                short_doi = self.value.replace("https://doi.org/", "")
                full_doi = self.value
            else:
                # Short form, create the full URL
                short_doi = self.value
                full_doi = f"https://doi.org/{self.value}"
            
            # Query both formats with OR
            q = Q("term", **{self.es_field(): full_doi}) | Q("term", **{self.es_field(): short_doi})
        elif self.param in id_params:
            formatted_id = self.format_id()
            if formatted_id is None:
                raise APIQueryParamsError(
                    f"{self.value} is not a valid ID for {self.param}"
                )
            kwargs = {self.es_field(): formatted_id}
            q = Q("term", **kwargs)
        else:
            kwargs = {self.es_field(): self.value}
            q = Q("term", **kwargs)
        return q

    def es_field(self) -> str:
        if self.custom_es_field:
            field = self.custom_es_field
        elif self.param == "doi":
            # Special case for DOI: use ids.doi directly without .lower
            field = "ids.doi"
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
            self.param
            in [
                "affiliations.institution.ror",
                "authorships.institutions.ror",
                "institutions.ror",
                "ror",
            ]
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
                c["country_code"] for c in country_list.COUNTRIES_BY_CONTINENT["Africa"]
            ]
        elif (
            continent == "antarctica"
            or continent.upper() == CONTINENT_PARAMS["antarctica"]
        ):
            country_codes = [
                c["country_code"]
                for c in country_list.COUNTRIES_BY_CONTINENT["Antarctica"]
            ]
        elif continent == "asia" or continent.upper() == CONTINENT_PARAMS["asia"]:
            country_codes = [
                c["country_code"] for c in country_list.COUNTRIES_BY_CONTINENT["Asia"]
            ]
        elif continent == "europe" or continent.upper() == CONTINENT_PARAMS["europe"]:
            country_codes = [
                c["country_code"] for c in country_list.COUNTRIES_BY_CONTINENT["Europe"]
            ]
        elif (
            continent == "north_america"
            or continent.upper() == CONTINENT_PARAMS["north_america"]
        ):
            country_codes = [
                c["country_code"]
                for c in country_list.COUNTRIES_BY_CONTINENT["North America"]
            ]
        elif continent == "oceania" or continent.upper() == CONTINENT_PARAMS["oceania"]:
            country_codes = [
                c["country_code"]
                for c in country_list.COUNTRIES_BY_CONTINENT["Oceania"]
            ]
        elif (
            continent == "south_america"
            or continent.upper() == CONTINENT_PARAMS["south_america"]
        ):
            country_codes = [
                c["country_code"]
                for c in country_list.COUNTRIES_BY_CONTINENT["South America"]
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


class ExternalIDField(Field):
    """
    Field for handling special OpenAlex entity IDs like languages, countries, 
    licenses, and continents that don't follow the standard W123/A456 format.
    
    Accepts both formats:
    - Short form: languages/en, countries/us, licenses/cc-by
    - Full form: https://openalex.org/languages/en
    """
    
    def __init__(self, param, entity_type, **kwargs):
        super().__init__(param, **kwargs)
        self.entity_type = entity_type
    
    def build_query(self):
        # Handle null values
        if self.value == "null":
            field_name = self.es_field()
            field_name = field_name.replace("__", ".")
            return ~Q("exists", field=field_name)
        elif self.value == "!null":
            field_name = self.es_field()
            field_name = field_name.replace("__", ".")
            return Q("exists", field=field_name)
        
        # Handle negation
        if self.value.startswith("!"):
            query_value = self.value[1:]
            formatted_value = self._format_id(query_value)
            kwargs = {self.es_field(): formatted_value}
            return ~Q("term", **kwargs)
        else:
            formatted_value = self._format_id(self.value)
            kwargs = {self.es_field(): formatted_value}
            return Q("term", **kwargs)
    
    def es_field(self) -> str:
        """Use the same field mapping pattern as TermField."""
        if self.custom_es_field:
            field = self.custom_es_field
        elif self.alias:
            field = self.alias.replace(".", "__") + "__lower"
        elif "." in self.param:
            field = self.param.replace(".", "__") + "__lower"
        else:
            field = self.param + "__lower"
        return field
    
    def _format_id(self, value):
        """Format ID to the full URL format expected in Elasticsearch."""
        # If already a full URL, return as-is
        if value.startswith("https://openalex.org/"):
            return value
        
        # If it has the entity prefix, add the base URL
        if value.startswith(f"{self.entity_type}/"):
            return f"https://openalex.org/{value}"
        
        # If it's just the bare code, add both entity prefix and base URL
        return f"https://openalex.org/{self.entity_type}/{value}"
    
    def validate(self, query):
        """Validate that the ID format is correct for this entity type."""
        clean_value = query
        if clean_value.startswith("!"):
            clean_value = clean_value[1:]
        
        if clean_value in ["null", "!null"]:
            return
        
        # Remove URL prefix for validation
        if clean_value.startswith("https://openalex.org/"):
            clean_value = clean_value.replace("https://openalex.org/", "")
        
        # Check if it's a valid format for this entity type
        if not (clean_value.startswith(f"{self.entity_type}/") or 
                "/" not in clean_value):  # Allow bare codes like "en", "us"
            raise APIQueryParamsError(
                f"'{query}' is not a valid {self.entity_type} ID. Expected format: "
                f"{self.entity_type}/code or https://openalex.org/{self.entity_type}/code"
            )
