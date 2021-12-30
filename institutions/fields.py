from core.field import Field

fields = [
    Field(param="cited_by_count", is_range_query=True),
    Field(param="country_code"),
    Field(param="display_name", is_search_exact_query=True),
    Field(param="display_name.search", is_search_query=True),
    Field(param="type"),
    Field(param="works_count", is_range_query=True),
    Field(param="x_concepts.id"),
]

fields_dict = {f.param: f for f in fields}
