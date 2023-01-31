from core.fields import (DateField, OpenAlexIDField, RangeField, SearchField,
                         TermField)

fields = [
    DateField(
        param="from_created_date",
        custom_es_field="created_date",
    ),
    DateField(
        param="from_updated_date",
        custom_es_field="updated_date",
    ),
    OpenAlexIDField(param="openalex", custom_es_field="ids.openalex.lower"),
    OpenAlexIDField(param="openalex_id", alias="ids.openalex"),
    OpenAlexIDField(
        param="parent_publisher", custom_es_field="parent_publisher.keyword"
    ),
    RangeField(param="cited_by_count"),
    RangeField(param="hierarchy_level"),
    RangeField(param="works_count"),
    SearchField(param="display_name.search"),
    TermField(param="country_code", custom_es_field="country_codes.lower"),
    TermField(
        param=f"continent",
        custom_es_field="country_codes.lower",
    ),
    TermField(param="display_name", custom_es_field="display_name.keyword"),
    TermField(param="ror", custom_es_field="ids.ror.lower"),
    TermField(
        param="wikidata_id",
        custom_es_field="ids.wikidata.lower",
        unique_id="wikidata_entity",
    ),
]

fields_dict = {f.param: f for f in fields}
