from core.fields import (
    BooleanField,
    DateField,
    DateTimeField,
    OpenAlexIDField,
    PhraseField,
    RangeField,
    SearchField,
    TermField,
)

fields = [
    BooleanField(param="has_issn", custom_es_field="ids.issn_l"),
    BooleanField(
        param="is_in_doaj",
        docstring="Filter for only journals that are in DOAJ, the Directory of Open Access Journals",
        documentation_link="https://docs.openalex.org/api-entities/sources/source-object#is_in_doaj",
    ),
    BooleanField(
        param="is_oa",
        docstring="Filter only sources that are currently Open Access",
        documentation_link="https://docs.openalex.org/api-entities/sources/source-object#is_oa",
    ),
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
    OpenAlexIDField(param="concept.id", custom_es_field="x_concepts.id"),
    OpenAlexIDField(param="concepts.id", custom_es_field="x_concepts.id"),
    OpenAlexIDField(param="host_organization"),
    OpenAlexIDField(
        param="host_organization.id", custom_es_field="host_organization.lower"
    ),
    OpenAlexIDField(param="host_organization_lineage"),
    OpenAlexIDField(
        param="ids.openalex",
        docstring="The OpenAlex ID for a source",
        documentation_link="https://docs.openalex.org/how-to-use-the-api/get-single-entities#the-openalex-id",
    ),
    OpenAlexIDField(param="openalex", custom_es_field="ids.openalex.lower"),
    OpenAlexIDField(param="openalex_id", alias="ids.openalex"),
    OpenAlexIDField(
        param="x_concepts.id",
        docstring="Filter for sources that have works that tend to be about a given Concept",
        documentation_link="https://docs.openalex.org/api-entities/concepts",
    ),
    RangeField(param="apc_usd"),
    RangeField(param="apc_prices.price"),
    RangeField(param="cited_by_count"),
    RangeField(param="summary_stats.2yr_mean_citedness"),
    RangeField(param="summary_stats.h_index"),
    RangeField(param="summary_stats.i10_index"),
    RangeField(param="works_count"),
    SearchField(param="default.search", index="sources"),
    SearchField(
        param="display_name.search",
        docstring="Free text search among sources' names",
        documentation_link="https://docs.openalex.org/api-entities/sources/search-sources#search-a-specific-field",
    ),
    TermField(
        param="apc_prices.currency",
    ),
    TermField(
        param=f"continent",
        custom_es_field="country_code",
    ),
    TermField(param="country_code"),
    TermField(param="display_name", custom_es_field="display_name.keyword"),
    TermField(param="ids.mag", custom_es_field="ids.mag"),
    TermField(param="issn"),
    TermField(
        param="type",
        docstring="Filter by source type. For example, filter for only journals, or only repositories.",
        documentation_link="https://docs.openalex.org/api-entities/sources/source-object#type",
    ),
]

fields_dict = {f.param: f for f in fields}
