from core.field import Field

fields = [
    Field(param="works_count", is_range_query=True),
    Field(param="cited_by_count", is_range_query=True),
    Field(param="last_known_institution.id"),
    Field(param="last_known_institution.ror"),
    Field(param="last_known_institution.country_code"),
    Field(param="last_known_institution.type"),
    Field(param="x_concepts.id"),
    Field(param="display_name", is_search_exact_query=True),
    Field(param="display_name.search", is_search_query=True),
]

fields_dict = {f.param: f for f in fields}
