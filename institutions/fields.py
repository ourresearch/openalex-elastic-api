import settings
from core.fields import (BooleanField, DateField, OpenAlexIDField, RangeField,
                         SearchField, TermField)

fields = [
    BooleanField(param="has_ror", custom_es_field="ids.ror.keyword"),
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
    OpenAlexIDField(param="x_concepts.id"),
    RangeField(param="cited_by_count"),
    RangeField(param="works_count"),
    SearchField(param="display_name.search"),
    TermField(param="country_code"),
    TermField(param="display_name", custom_es_field="display_name.keyword"),
    TermField(param="ror", alias="ror"),
    TermField(param="type"),
]

# add country group filters
for param in settings.COUNTRY_PARAMS:
    fields.append(
        BooleanField(
            param=f"country_code.{param}",
            custom_es_field="country_code",
        )
    )

fields_dict = {f.param: f for f in fields}
