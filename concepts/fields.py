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
    BooleanField(param="has_wikidata", custom_es_field="ids.wikidata"),
    DateField(
        param="from_created_date",
        custom_es_field="created_date",
    ),
    DateTimeField(
        param="from_updated_date",
        custom_es_field="updated_date",
    ),
    OpenAlexIDField(param="ancestors.id"),
    OpenAlexIDField(
        param="ids.openalex",
        custom_es_field="ids.openalex.lower",
        docstring="The OpenAlex ID for a concept",
        documentation_link="https://docs.openalex.org/how-to-use-the-api/get-single-entities#the-openalex-id",
    ),
    OpenAlexIDField(param="openalex", custom_es_field="ids.openalex.lower"),
    OpenAlexIDField(param="openalex_id", alias="ids.openalex"),
    RangeField(param="summary_stats.2yr_mean_citedness"),
    RangeField(param="cited_by_count"),
    RangeField(param="summary_stats.h_index"),
    RangeField(param="summary_stats.i10_index"),
    RangeField(
        param="level",
        docstring="Filter by concept level. Lower-level concepts are more general, and higher-level concepts are more specific.",
        documentation_link="https://docs.openalex.org/api-entities/concepts/concept-object#level",
    ),
    RangeField(param="works_count"),
    SearchField(param="default.search", index="concepts"),
    SearchField(
        param="display_name.search",
        docstring="Free text search among concepts' names",
        documentation_link="https://docs.openalex.org/api-entities/concepts/search-concepts#search-a-specific-field",
    ),
    TermField(param="display_name", custom_es_field="display_name.keyword"),
    TermField(param="wikidata_id", alias="ids.wikidata"),
]

fields_dict = {f.param: f for f in fields}
