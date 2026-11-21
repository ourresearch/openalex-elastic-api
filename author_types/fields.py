"""Filters for /author-types: what kind of agent an author is (human, organization, software-agent;
oxjob #2437). A small closed vocabulary with its own endpoint, shaped like /relationships."""
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
    "openalex": "The OpenAlex ID for the author type",
}

DOCUMENTATION_LINKS = {
    "openalex": "https://help.openalex.org/data/author-types/",
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
        entity_type="author-types",
        docstring=DOCSTRINGS["openalex"],
        documentation_link=DOCUMENTATION_LINKS["openalex"],
        alternate_names=ALTERNATE_NAMES.get("openalex", None),
    ),
    RangeField(param="works_count"),
    SearchField(param="text.search", index="author-types"),
    SearchField(param="default.search", index="author-types", alternate_of="text.search"),
    SearchField(
        param="display_name.search",
        docstring="Free text search among author types' names",
        documentation_link="https://developers.openalex.org/guides/searching",
    ),
    TermField(param="display_name", custom_es_field="display_name.keyword"),
    CollectionField(entity_type="author-types"),
]

fields_dict = {f.param: f for f in fields}
