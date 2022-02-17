from core.fields import (DateField, OpenAlexIDField, RangeField, SearchField,
                         TermField)

fields = [
    DateField(
        param="from_created_date",
        custom_es_field="created_date",
    ),
    OpenAlexIDField(param="last_known_institution.id"),
    OpenAlexIDField(param="x_concepts.id"),
    RangeField(param="cited_by_count"),
    RangeField(param="works_count"),
    SearchField(param="display_name.search"),
    TermField(param="display_name"),
    TermField(param="last_known_institution.country_code"),
    TermField(param="last_known_institution.ror"),
    TermField(param="last_known_institution.type"),
]

fields_dict = {f.param: f for f in fields}
