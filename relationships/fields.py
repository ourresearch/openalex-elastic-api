"""Filters for /relationships: the kinds of link between a work and its parent work
(oxjob #2065). A small entity with its own endpoint, like /types."""
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
    "openalex": "The OpenAlex ID for the relationship",
}

DOCUMENTATION_LINKS = {
    "openalex": "https://help.openalex.org/data/relationships/",
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
        entity_type="relationships",
        docstring=DOCSTRINGS["openalex"],
        documentation_link=DOCUMENTATION_LINKS["openalex"],
        alternate_names=ALTERNATE_NAMES.get("openalex", None),
    ),
    RangeField(param="works_count"),
    SearchField(param="text.search", index="relationships"),
    SearchField(param="default.search", index="relationships", alternate_of="text.search"),
    SearchField(
        param="display_name.search",
        docstring="Free text search among relationships' names",
        documentation_link="https://developers.openalex.org/guides/searching",
    ),
    TermField(param="display_name", custom_es_field="display_name.keyword"),
    CollectionField(entity_type="relationships"),
]

fields_dict = {f.param: f for f in fields}
