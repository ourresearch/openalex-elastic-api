from core.field import Field

fields = [
    Field(param="display_name", is_search_exact_query=True),
    Field(param="display_name.search", is_search_query=True),
    Field(param="cited_by_count", is_range_query=True),
    Field(param="is_in_doaj", is_bool_query=True),
    Field(param="is_oa", is_bool_query=True),
    Field(param="issn", custom_es_field="issn__lower"),
    Field(param="publisher", custom_es_field="publisher__lower"),
    Field(param="works_count", is_range_query=True),
    Field(param="x_concepts.id", custom_es_field="x_concepts__id__lower"),
]

fields_dict = {f.param: f for f in fields}
