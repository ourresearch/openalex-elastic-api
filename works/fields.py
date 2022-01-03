from core.field import Field

fields = [
    Field(param="publication_year", is_range_query=True),
    Field(param="publication_date", is_date_query=True),
    Field(param="host_venue.id", custom_es_field="host_venue__id__lower"),
    Field(param="journal.id", custom_es_field="host_venue__id__lower"),
    Field(param="host_venue.issn", custom_es_field="host_venue__issn__lower"),
    Field(
        param="host_venue.publisher", custom_es_field="host_venue__publisher__keyword"
    ),
    Field(param="type", custom_es_field="type__lower"),
    Field(param="is_paratext", is_bool_query=True),
    Field(
        param="open_access.oa_status", custom_es_field="open_access__oa_status__lower"
    ),
    Field(param="oa_status", custom_es_field="open_access__oa_status__lower"),
    Field(param="open_access.is_oa", is_bool_query=True),
    Field(param="is_oa", custom_es_field="open_access__is_oa", is_bool_query=True),
    Field(param="author.id", custom_es_field="authorships__author__id__lower"),
    Field(param="author.orcid", custom_es_field="authorships__author__orcid__lower"),
    Field(
        param="authorships.author.id", custom_es_field="authorships__author__id__lower"
    ),
    Field(
        param="authorships.author.orcid",
        custom_es_field="authorships__author__orcid__lower",
    ),
    Field(
        param="institutions.id", custom_es_field="authorships__institutions__id__lower"
    ),
    Field(
        param="institution.id", custom_es_field="authorships__institutions__id__lower"
    ),
    Field(
        param="institutions.ror",
        custom_es_field="authorships__institutions__ror__lower",
    ),
    Field(
        param="institutions.country_code",
        custom_es_field="authorships__institutions__country_code__lower",
    ),
    Field(
        param="institutions.type",
        custom_es_field="authorships__institutions__type__lower",
    ),
    Field(
        param="authorships.institutions.id",
        custom_es_field="authorships__institutions__id__lower",
    ),
    Field(
        param="authorships.institutions.ror",
        custom_es_field="authorships__institutions__ror__lower",
    ),
    Field(
        param="authorships.institutions.country_code",
        custom_es_field="authorships__institutions__country_code__lower",
    ),
    Field(
        param="authorships.institutions.type",
        custom_es_field="authorships__institutions__type__lower",
    ),
    Field(param="cited_by_count", is_range_query=True),
    Field(param="is_retracted", is_bool_query=True),
    Field(param="concepts.id", custom_es_field="concepts__id__lower"),
    Field(param="concept.id", custom_es_field="concepts__id__lower"),
    Field(param="concepts.wikidata", custom_es_field="concepts__wikidata__lower"),
    Field(
        param="alternate_host_venues.license",
        custom_es_field="alternate_host_venues__license__lower",
    ),
    Field(
        param="alternate_host_venues.version",
        custom_es_field="alternate_host_venues__version__lower",
    ),
    Field(
        param="alternate_host_venues.venue_id",
        custom_es_field="alternate_host_venues__venue_id__lower",
    ),
    Field(param="referenced_works", custom_es_field="referenced_works__lower"),
    Field(param="cites", custom_es_field="referenced_works__lower"),
    Field(param="display_name", is_search_exact_query=True),
    Field(param="display_name.search", is_search_query=True),
    Field(param="title.search", is_search_query=True),
]

fields_dict = {f.param: f for f in fields}
