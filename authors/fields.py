from core.fields import OpenAlexIDField, RangeField, SearchField, TermField

fields = [
    TermField(param="display_name"),
    SearchField(param="display_name.search"),
    RangeField(param="cited_by_count"),
    TermField(
        param="last_known_institution.country_code",
        custom_es_field="last_known_institution__country_code__lower",
    ),
    OpenAlexIDField(
        param="last_known_institution.id",
        custom_es_field="last_known_institution__id__lower",
    ),
    TermField(
        param="last_known_institution.ror",
        custom_es_field="last_known_institution__ror__lower",
    ),
    TermField(
        param="last_known_institution.type",
        custom_es_field="last_known_institution__type__lower",
    ),
    RangeField(param="works_count"),
    OpenAlexIDField(param="x_concepts.id", custom_es_field="x_concepts__id__lower"),
]

fields_dict = {f.param: f for f in fields}
