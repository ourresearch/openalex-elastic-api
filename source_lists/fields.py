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

# shared docstrings for when multiple fields share the same docstring (such as aliases)
DOCSTRINGS = {
    "openalex": "The OpenAlex ID for the source list",
}

# shared documentation_links for when multiple fields share the same link (such as aliases)
DOCUMENTATION_LINKS = {
    "openalex": "https://help.openalex.org/data/source-lists/",
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
    ExternalIDField(
        param="id",
        entity_type="source-lists",
        docstring=DOCSTRINGS["openalex"],
        documentation_link=DOCUMENTATION_LINKS["openalex"],
        alternate_names=ALTERNATE_NAMES.get("openalex", None),
    ),
    RangeField(param="cited_by_count"),
    RangeField(param="sources_count"),
    RangeField(param="works_count"),
    SearchField(param="text.search", index="source-lists"),
    SearchField(param="default.search", index="source-lists", alternate_of="text.search"),
    SearchField(
        param="display_name.search",
        docstring="Free text search among source lists' names",
        documentation_link="https://developers.openalex.org/guides/searching",
    ),
    TermField(param="display_name", custom_es_field="display_name.keyword"),
    TermField(
        param="maintainer",
        custom_es_field="maintainer.keyword",
        docstring="The organisation that maintains the list",
    ),
    CollectionField(entity_type="source-lists"),
]

fields_dict = {f.param: f for f in fields}
