from core.fields import (BooleanField, DateField, DateTimeField,
                         OpenAlexIDField, RangeField, SearchField, TermField)

fields = [
    BooleanField(
        param=f"is_global_south",
        custom_es_field="country_code",
    ),
    BooleanField(param="has_ror", custom_es_field="ids.ror.keyword"),
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
    OpenAlexIDField(param="openalex", custom_es_field="ids.openalex.lower"),
    OpenAlexIDField(param="openalex_id", alias="ids.openalex"),
    OpenAlexIDField(
        param="repositories.host_organization",
        custom_es_field="repositories.host_organization.keyword",
    ),
    OpenAlexIDField(
        param="repositories.host_organization_lineage",
        alias="repositories.host_organization_lineage.keyword",
    ),
    OpenAlexIDField(param="repositories.id", custom_es_field="repositories.id.keyword"),
    OpenAlexIDField(param="x_concepts.id"),
    RangeField(param="summary_stats.2yr_mean_citedness"),
    RangeField(param="cited_by_count"),
    RangeField(param="summary_stats.h_index"),
    RangeField(param="summary_stats.i10_index"),
    RangeField(param="works_count"),
    SearchField(param="display_name.search"),
    TermField(param="country_code"),
    TermField(
        param=f"continent",
        custom_es_field="country_code",
    ),
    TermField(param="display_name", custom_es_field="display_name.keyword"),
    TermField(param="ror", alias="ror"),
    TermField(param="type"),
]

fields_dict = {f.param: f for f in fields}
