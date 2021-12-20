from dataclasses import dataclass
from typing import Optional


@dataclass
class Field:
    """
    Defines a field that can be filtered, grouped, and sorted.
    """

    param: str
    custom_es_field: Optional[str] = None
    is_bool_query: bool = False
    is_date_query: bool = False
    is_range_query: bool = False

    def es_field(self) -> str:
        if self.custom_es_field:
            field = self.custom_es_field
        elif "." in self.param:
            field = self.param.replace(".", "__")
        else:
            field = self.param
        return field


fields = [
    Field(param="publication_year", is_range_query=True),
    Field(param="publication_date", is_date_query=True),
    Field(param="venue.issn"),
    Field(param="venue.publisher"),
    Field(param="genre"),
    Field(param="is_paratext", is_bool_query=True),
    Field(param="oa_status"),
    Field(param="is_oa", is_bool_query=True),
    Field(param="author.id", custom_es_field="authorships__author__id"),
    Field(param="author.orcid", custom_es_field="authorships__author__orcid"),
    Field(param="institutions.id", custom_es_field="authorships__institutions__id"),
    Field(param="institutions.ror", custom_es_field="authorships__institutions__ror"),
    Field(
        param="institutions.country_code",
        custom_es_field="authorships__institutions__country_code",
    ),
    Field(param="institutions.type", custom_es_field="authorships__institutions__type"),
    Field(param="cited_by_count", is_range_query=True),
    Field(param="is_retracted", is_bool_query=True),
    Field(param="concepts.id"),
    Field(param="concepts.wikidata"),
    Field(param="alternate_locations.license"),
    Field(param="alternate_locations.version"),
    Field(param="alternate_locations.venue_id"),
    Field(param="referenced_works"),
]
