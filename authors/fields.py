from core.fields import (BooleanField, DateField, OpenAlexIDField, RangeField,
                         SearchField, TermField)

fields = [
    BooleanField(param="has_orcid", custom_es_field="ids.orcid"),
    DateField(
        param="from_created_date",
        custom_es_field="created_date",
    ),
    DateField(
        param="from_updated_date",
        custom_es_field="updated_date",
    ),
    OpenAlexIDField(param="last_known_institution.id"),
    OpenAlexIDField(param="x_concepts.id"),
    RangeField(param="cited_by_count"),
    RangeField(param="works_count"),
    SearchField(param="display_name.search"),
    TermField(param="display_name", custom_es_field="display_name.keyword"),
    TermField(param="last_known_institution.country_code"),
    TermField(param="last_known_institution.ror"),
    TermField(param="last_known_institution.type"),
    TermField(param="openalex_id", alias="ids.openalex"),
    TermField(param="orcid", alias="ids.orcid"),
]

fields_dict = {f.param: f for f in fields}
