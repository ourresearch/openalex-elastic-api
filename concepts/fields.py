from core.field import Field

fields = [
    Field(param="ancestors.id"),
    Field(param="cited_by_count", is_range_query=True),
    Field(param="display_name", is_search_exact_query=True),
    Field(param="display_name.search", is_search_query=True),
    Field(param="level", is_range_query=True),
    Field(param="works_count", is_range_query=True),
]

fields_dict = {f.param: f for f in fields}
