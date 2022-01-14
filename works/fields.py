from core.fields import (BooleanField, DateField, OpenAlexIDField, PhraseField,
                         RangeField, SearchField, TermField)

fields = [
    TermField(param="display_name"),
    SearchField(param="display_name.search"),
    SearchField(param="title.search"),
    OpenAlexIDField(
        param="alternate_host_venues.id", custom_es_field="alternate_host_venues__id"
    ),  # needs lower field
    TermField(param="alternate_host_venues.license"),
    TermField(param="alternate_host_venues.version"),
    OpenAlexIDField(param="authorships.author.id"),
    TermField(param="authorships.author.orcid"),
    OpenAlexIDField(param="authorships.institutions.id"),
    TermField(param="authorships.institutions.ror"),
    TermField(param="authorships.institutions.country_code"),
    TermField(param="authorships.institutions.type"),
    OpenAlexIDField(
        param="author.id", custom_es_field="authorships__author__id__lower"
    ),
    TermField(
        param="author.orcid", custom_es_field="authorships__author__orcid__lower"
    ),
    RangeField(param="cited_by_count"),
    OpenAlexIDField(param="cites", custom_es_field="referenced_works__lower"),
    OpenAlexIDField(param="concepts.id"),
    OpenAlexIDField(param="concept.id", custom_es_field="concepts__id__lower"),
    TermField(param="concepts.wikidata"),
    DateField(
        param="from_publication_date",
        custom_es_field="publication_date",
    ),
    BooleanField(param="is_retracted"),
    OpenAlexIDField(param="host_venue.id"),
    TermField(param="host_venue.issn"),
    PhraseField(param="host_venue.publisher"),
    TermField(
        param="institutions.country_code",
        custom_es_field="authorships__institutions__country_code__lower",
    ),
    OpenAlexIDField(
        param="institution.id", custom_es_field="authorships__institutions__id__lower"
    ),
    OpenAlexIDField(
        param="institutions.id", custom_es_field="authorships__institutions__id__lower"
    ),
    TermField(
        param="institutions.ror",
        custom_es_field="authorships__institutions__ror__lower",
    ),
    TermField(
        param="institutions.type",
        custom_es_field="authorships__institutions__type__lower",
    ),
    BooleanField(param="is_oa", custom_es_field="open_access__is_oa"),
    BooleanField(param="is_paratext"),
    OpenAlexIDField(param="journal.id", custom_es_field="host_venue__id__lower"),
    BooleanField(param="open_access.is_oa"),
    TermField(param="open_access.oa_status"),
    TermField(param="oa_status", custom_es_field="open_access__oa_status__lower"),
    DateField(param="publication_date"),
    RangeField(param="publication_year"),
    OpenAlexIDField(param="referenced_works"),
    DateField(
        param="to_publication_date",
        custom_es_field="publication_date",
    ),
    TermField(param="type"),
]

fields_dict = {f.param: f for f in fields}
