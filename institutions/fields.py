from core.field import Field

fields = [
    Field(param="cited_by_count", is_range_query=True),
    Field(param="country_code", custom_es_field="country_code__lower"),
    Field(param="display_name", is_search_exact_query=True),
    Field(param="display_name.search", is_search_query=True),
    Field(param="type", custom_es_field="type__lower"),
    Field(param="works_count", is_range_query=True),
    Field(param="x_concepts.id", custom_es_field="x_concepts__id__lower"),
]

fields_dict = {f.param: f for f in fields}
