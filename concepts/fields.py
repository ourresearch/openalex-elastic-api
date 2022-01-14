from core.fields import OpenAlexIDField, RangeField, SearchField, TermField

fields = [
    TermField(param="display_name"),
    SearchField(param="display_name.search"),
    OpenAlexIDField(param="ancestors.id"),
    RangeField(param="cited_by_count"),
    RangeField(param="level"),
    RangeField(param="works_count"),
]

fields_dict = {f.param: f for f in fields}
