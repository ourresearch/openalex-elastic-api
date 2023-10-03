from core.fields import (
    BooleanField,
    DateField,
    DateTimeField,
    OpenAlexIDField,
    RangeField,
    SearchField,
    TermField,
)

fields = [
    BooleanField(
        param=f"is_global_south",
        custom_es_field="country_code",
    ),
    DateField(
        param="from_created_date",
        custom_es_field="created_date",
    ),
    DateTimeField(
        param="from_updated_date",
        custom_es_field="updated_date",
    ),
    OpenAlexIDField(
        param="ids.openalex",
        custom_es_field="ids.openalex.lower",
        docstring="The OpenAlex ID for the funder",
        documentation_link="https://docs.openalex.org/how-to-use-the-api/get-single-entities#the-openalex-id",
    ),
    OpenAlexIDField(param="ids.openalex"),
    OpenAlexIDField(param="openalex", custom_es_field="ids.openalex.lower"),
    OpenAlexIDField(param="openalex_id", alias="ids.openalex"),
    OpenAlexIDField(param="roles.id"),
    RangeField(param="summary_stats.2yr_mean_citedness"),
    RangeField(param="cited_by_count"),
    RangeField(param="grants_count"),
    RangeField(param="summary_stats.h_index"),
    RangeField(param="summary_stats.i10_index"),
    RangeField(param="works_count"),
    SearchField(param="default.search", index="funders"),
    SearchField(param="description.search", custom_es_field="description"),
    SearchField(
        param="display_name.search",
        docstring="Free text search among funders' names",
        documentation_link="https://docs.openalex.org/api-entities/funders/search-funders#search-a-specific-field",
    ),
    TermField(
        param=f"continent",
        custom_es_field="country_code",
    ),
    TermField(param="country_code"),
    TermField(param="display_name", custom_es_field="display_name.keyword"),
    TermField(param="ids.ror", custom_es_field="ids.ror.lower"),
    TermField(
        param="ids.wikidata",
        custom_es_field="ids.wikidata.lower",
        unique_id="wikidata_entity",
    ),
    TermField(param="ror", custom_es_field="ids.ror.lower"),
    TermField(
        param="wikidata",
        custom_es_field="ids.wikidata.lower",
        unique_id="wikidata_entity",
    ),
    TermField(param="ids.crossref", custom_es_field="ids.crossref"),
    TermField(param="ids.doi", custom_es_field="ids.doi.keyword"),
]

fields_dict = {f.param: f for f in fields}
