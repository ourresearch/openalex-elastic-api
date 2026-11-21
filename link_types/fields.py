"""Filters for /link-types: the kinds of link between two works (citation, review, and the part-of kinds of
parent_works). The new name of /relationships, the same vocabulary (oxjob #2481); both answer until the cutover."""
from core.fields import (
    CollectionField,
    DateField,
    DateTimeField,
    ExternalIDField,
    RangeField,
    SearchField,
    TermField,
)
from core.alternate_names import ALTERNATE_NAMES

DOCSTRINGS = {
    "openalex": "The OpenAlex ID for the link type",
}

DOCUMENTATION_LINKS = {
    "openalex": "https://help.openalex.org/data/link-types/",
}

fields = [
    DateField(
        param="from_created_date",
        custom_es_field="created_date",
    ),
    DateTimeField(
        param="from_updated_date",
        custom_es_field="updated_date",
    ),
    DateField(
        param="to_created_date",
        custom_es_field="created_date",
    ),
    DateTimeField(
        param="to_updated_date",
        custom_es_field="updated_date",
    ),
    ExternalIDField(
        param="id",
        entity_type="link-types",
        docstring=DOCSTRINGS["openalex"],
        documentation_link=DOCUMENTATION_LINKS["openalex"],
        alternate_names=ALTERNATE_NAMES.get("openalex", None),
    ),
    RangeField(param="works_count"),
    SearchField(param="text.search", index="link-types"),
    SearchField(param="default.search", index="link-types", alternate_of="text.search"),
    SearchField(
        param="display_name.search",
        docstring="Free text search among link types' names",
        documentation_link="https://developers.openalex.org/guides/searching",
    ),
    TermField(param="display_name", custom_es_field="display_name.keyword"),
    CollectionField(entity_type="link-types"),
]

fields_dict = {f.param: f for f in fields}
