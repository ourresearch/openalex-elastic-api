from core.fields import OpenAlexIDField, RangeField, SearchField, TermField

fields = [
    TermField(param="display_name"),
    SearchField(param="display_name.search"),
    RangeField(param="cited_by_count"),
    TermField(param="last_known_institution.country_code"),
    OpenAlexIDField(param="last_known_institution.id"),
    TermField(param="last_known_institution.ror"),
    TermField(param="last_known_institution.type"),
    RangeField(param="works_count"),
    OpenAlexIDField(param="x_concepts.id"),
]

fields_dict = {f.param: f for f in fields}
