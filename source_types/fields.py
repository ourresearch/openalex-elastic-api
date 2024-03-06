from core.fields import (
    DateField,
    DateTimeField,
    OpenAlexIDField,
    RangeField,
    SearchField,
    TermField,
)
from core.alternate_names import ALTERNATE_NAMES

# shared docstrings for when multiple fields share the same docstring (such as aliases)
DOCSTRINGS = {
    "openalex": "The OpenAlex ID for the source type",
}

# shared documentation_links for when multiple fields share the same link (such as aliases)
DOCUMENTATION_LINKS = {
    "openalex": "https://docs.openalex.org/how-to-use-the-api/get-single-entities#the-openalex-id",
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
    OpenAlexIDField(
        param="id",
        docstring=DOCSTRINGS["openalex"],
        documentation_link=DOCUMENTATION_LINKS["openalex"],
        alternate_names=ALTERNATE_NAMES.get("openalex", None),
    ),
    OpenAlexIDField(
        param="openalex",
        custom_es_field="id.lower",
        docstring=DOCSTRINGS["openalex"],
        documentation_link=DOCUMENTATION_LINKS["openalex"],
        alternate_names=ALTERNATE_NAMES.get("openalex", None),
    ),
    RangeField(param="cited_by_count"),
    RangeField(param="works_count"),
    SearchField(param="default.search", index="types"),
    SearchField(
        param="display_name.search",
        docstring="Free text search among types' names",
        documentation_link="https://docs.openalex.org/api-entities/types/search-types#search-a-specific-field",
    ),
    TermField(param="display_name", custom_es_field="display_name.keyword"),
]

fields_dict = {f.param: f for f in fields}
