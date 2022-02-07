from core.fields import OpenAlexIDField, RangeField, SearchField, TermField

fields = [
    OpenAlexIDField(param="x_concepts.id"),
    RangeField(param="cited_by_count"),
    RangeField(param="works_count"),
    SearchField(param="display_name.search"),
    TermField(param="country_code"),
    TermField(param="display_name"),
    TermField(param="type"),
]

fields_dict = {f.param: f for f in fields}
