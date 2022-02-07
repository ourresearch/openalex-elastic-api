from core.fields import OpenAlexIDField, RangeField, SearchField, TermField

fields = [
    OpenAlexIDField(param="ancestors.id"),
    RangeField(param="cited_by_count"),
    RangeField(param="level"),
    RangeField(param="works_count"),
    SearchField(param="display_name.search"),
    TermField(param="display_name"),
]

fields_dict = {f.param: f for f in fields}
