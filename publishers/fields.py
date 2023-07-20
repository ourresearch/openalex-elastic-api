from core.fields import (DateField, DateTimeField, OpenAlexIDField, RangeField,
                         SearchField, TermField)

fields = [
    DateField(
        param="from_created_date",
        custom_es_field="created_date",
    ),
    DateTimeField(
        param="from_updated_date",
        custom_es_field="updated_date",
    ),
    OpenAlexIDField(param="ids.openalex", custom_es_field="ids.openalex.lower"),
    OpenAlexIDField(param="lineage"),
    OpenAlexIDField(param="openalex", custom_es_field="ids.openalex.lower"),
    OpenAlexIDField(param="openalex_id", alias="ids.openalex"),
    OpenAlexIDField(
        param="parent_publisher", custom_es_field="parent_publisher.id.keyword"
    ),
    OpenAlexIDField(param="roles.id"),
    RangeField(param="summary_stats.2yr_mean_citedness"),
    RangeField(param="cited_by_count"),
    RangeField(param="summary_stats.h_index"),
    RangeField(param="hierarchy_level"),
    RangeField(param="summary_stats.i10_index"),
    RangeField(param="works_count"),
    SearchField(param="default.search", index="publishers"),
    SearchField(param="display_name.search"),
    TermField(param="country_codes", custom_es_field="country_codes.lower"),
    TermField(
        param=f"continent",
        custom_es_field="country_codes.lower",
    ),
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
]

fields_dict = {f.param: f for f in fields}
