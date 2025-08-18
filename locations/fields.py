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
    TermField(param="native_id", custom_es_field="native_id.keyword"),
    TermField(param="native_id_namespace", custom_es_field="native_id_namespace.keyword"),
    TermField(param="title", custom_es_field="title.keyword"),
    TermField(param="type", custom_es_field="type.keyword"),
    TermField(param="source_name", custom_es_field="source_name.keyword"),
    TermField(param="version", custom_es_field="version.keyword"),
    TermField(param="license", custom_es_field="license.keyword"),
    TermField(param="language", custom_es_field="language.keyword"),
    TermField(param="publisher", custom_es_field="publisher.keyword"),
]

fields_dict = {f.param: f for f in fields}