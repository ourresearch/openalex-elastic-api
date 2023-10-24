from core.fields import (
    BooleanField,
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
    "openalex": "The OpenAlex ID for the concept",
}

# shared documentation_links for when multiple fields share the same link (such as aliases)
DOCUMENTATION_LINKS = {
    "openalex": "https://docs.openalex.org/how-to-use-the-api/get-single-entities#the-openalex-id",
}

fields = [
    BooleanField(param="has_wikidata", custom_es_field="ids.wikidata"),
    DateField(
        param="from_created_date",
        custom_es_field="created_date",
    ),
    DateTimeField(
        param="from_updated_date",
        custom_es_field="updated_date",
    ),
    OpenAlexIDField(param="ancestors.id"),
    OpenAlexIDField(
        param="ids.openalex",
        custom_es_field="ids.openalex.lower",
        docstring=DOCSTRINGS["openalex"],
        documentation_link=DOCUMENTATION_LINKS["openalex"],
        alternate_names=ALTERNATE_NAMES.get("openalex", None),
    ),
    OpenAlexIDField(
        param="openalex",
        custom_es_field="ids.openalex.lower",
        docstring=DOCSTRINGS["openalex"],
        documentation_link=DOCUMENTATION_LINKS["openalex"],
        alternate_names=ALTERNATE_NAMES.get("openalex", None),
    ),
    OpenAlexIDField(
        param="openalex_id",
        alias="ids.openalex",
        docstring=DOCSTRINGS["openalex"],
        documentation_link=DOCUMENTATION_LINKS["openalex"],
        alternate_names=ALTERNATE_NAMES.get("openalex", None),
    ),
    RangeField(param="summary_stats.2yr_mean_citedness"),
    RangeField(param="cited_by_count"),
    RangeField(param="summary_stats.h_index"),
    RangeField(param="summary_stats.i10_index"),
    RangeField(
        param="level",
        docstring="The concept's level. Lower-level concepts are more general, and higher-level concepts are more specific.",
        documentation_link="https://docs.openalex.org/api-entities/concepts/concept-object#level",
        alternate_names=ALTERNATE_NAMES.get("concept.level", None),
    ),
    RangeField(param="works_count"),
    SearchField(param="default.search", index="concepts"),
    SearchField(
        param="display_name.search",
        docstring="Free text search among concepts' names",
        documentation_link="https://docs.openalex.org/api-entities/concepts/search-concepts#search-a-specific-field",
    ),
    TermField(param="display_name", custom_es_field="display_name.keyword"),
    TermField(param="wikidata_id", alias="ids.wikidata"),
]

fields_dict = {f.param: f for f in fields}
