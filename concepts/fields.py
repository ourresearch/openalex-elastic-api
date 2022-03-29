from core.fields import (BooleanField, DateField, OpenAlexIDField, RangeField,
                         SearchField, TermField)

fields = [
    BooleanField(param="has_wikidata", custom_es_field="ids.wikidata"),
    DateField(
        param="from_created_date",
        custom_es_field="created_date",
    ),
    DateField(
        param="from_updated_date",
        custom_es_field="updated_date",
    ),
    OpenAlexIDField(param="ancestors.id"),
    RangeField(param="cited_by_count"),
    RangeField(param="level"),
    RangeField(param="works_count"),
    SearchField(param="display_name.search"),
    TermField(param="display_name"),
]

fields_dict = {f.param: f for f in fields}
