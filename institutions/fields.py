from core.fields import OpenAlexIDField, RangeField, SearchField, TermField

fields = [
    TermField(param="display_name"),
    SearchField(param="display_name.search"),
    RangeField(param="cited_by_count"),
    TermField(param="country_code", custom_es_field="country_code__lower"),
    TermField(param="type", custom_es_field="type__lower"),
    RangeField(param="works_count"),
    OpenAlexIDField(param="x_concepts.id", custom_es_field="x_concepts__id__lower"),
]

fields_dict = {f.param: f for f in fields}
