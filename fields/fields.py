from core.fields import (
    DateField,
    DateTimeField,
    ExternalIDField,
    RangeField,
    SearchField,
    TermField,
)

fields = [
    DateField(
        param="from_created_date",
        custom_es_field="created_date",
    ),
    DateTimeField(
        param="from_updated_date",
        custom_es_field="updated_date",
    ),
    RangeField(param="cited_by_count"),
    ExternalIDField(
        param="id",
        entity_type="fields",
    ),
    RangeField(param="domain.id"),
    RangeField(param="subfields.id"),
    RangeField(param="works_count"),
    SearchField(param="default.search", index="fields"),
    SearchField(
        param="display_name.search",
        docstring="Free text search among fields' names",
        documentation_link="https://docs.openalex.org/api-entities/topics/search-topics#search-a-specific-field",
    ),
    TermField(param="display_name", custom_es_field="display_name.keyword"),
]

fields_dict = {f.param: f for f in fields}
