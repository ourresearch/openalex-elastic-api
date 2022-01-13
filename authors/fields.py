from core.field import Field

fields = [
    Field(param="display_name", is_search_exact_query=True),
    Field(param="display_name.search", is_search_query=True),
    Field(param="cited_by_count", is_range_query=True),
    Field(
        param="last_known_institution.country_code",
        custom_es_field="last_known_institution__country_code__lower",
    ),
    Field(
        param="last_known_institution.id",
        custom_es_field="last_known_institution__id__lower",
    ),
    Field(
        param="last_known_institution.ror",
        custom_es_field="last_known_institution__ror__lower",
    ),
    Field(
        param="last_known_institution.type",
        custom_es_field="last_known_institution__type__lower",
    ),
    Field(param="works_count", is_range_query=True),
    Field(param="x_concepts.id", custom_es_field="x_concepts__id__lower"),
]

fields_dict = {f.param: f for f in fields}
