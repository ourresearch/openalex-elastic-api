from core.field import Field

fields = [
    Field(param="publication_year", is_range_query=True),
    Field(param="publication_date", is_date_query=True),
    Field(param="host_venue.id"),
    Field(param="host_venue.issn"),
    Field(param="host_venue.publisher"),
    Field(param="type"),
    Field(param="is_paratext", is_bool_query=True),
    Field(param="open_access.oa_status"),
    Field(param="open_access.is_oa", is_bool_query=True),
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
    Field(param="alternate_host_venues.license"),
    Field(param="alternate_host_venues.version"),
    Field(param="alternate_host_venues.venue_id"),
    Field(param="referenced_works"),
]

fields_dict = {f.param: f for f in fields}
