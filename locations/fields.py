from core.fields import (
    BooleanField,
    OpenAlexIDField,
    SearchField,
    TermField,
)

fields = [
    BooleanField(
        param="is_oa",
        custom_es_field="is_oa",
        docstring="The location is open access",
    ),
    BooleanField(
        param="is_retracted",
        custom_es_field="is_retracted",
    ),
    OpenAlexIDField(
        param="work_id",
        custom_es_field="work_id",
    ),
    OpenAlexIDField(
        param="source_id",
        custom_es_field="source_id",
        docstring="The source where this location is found",
    ),
    SearchField(param="default.search", index="locations"),
    SearchField(
        param="title.search",
        unique_id="location_search",
    ),
    TermField(param="id", custom_es_field="id"),
    TermField(param="native_id", custom_es_field="native_id"),
    TermField(param="native_id_namespace", custom_es_field="native_id_namespace"),
    TermField(param='provenance', custom_es_field='provenance'),
    TermField(param="title", custom_es_field="title"),
    TermField(param="type", custom_es_field="type"),
    TermField(param="source_name", custom_es_field="source_name"),
    TermField(param="version", custom_es_field="version"),
    TermField(param="license", custom_es_field="license"),
    TermField(param="language", custom_es_field="language"),
    TermField(param="publisher", custom_es_field="publisher"),
]

fields_dict = {f.param: f for f in fields}