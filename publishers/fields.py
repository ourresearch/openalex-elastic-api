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
    "openalex": "The OpenAlex ID for the publisher",
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
        param="ids.openalex",
        custom_es_field="ids.openalex.lower",
        docstring=DOCSTRINGS["openalex"],
        documentation_link=DOCUMENTATION_LINKS["openalex"],
        alternate_names=ALTERNATE_NAMES.get("openalex", None),
    ),
    OpenAlexIDField(param="lineage"),
    OpenAlexIDField(
        param="openalex",
        docstring=DOCSTRINGS["openalex"],
        documentation_link=DOCUMENTATION_LINKS["openalex"],
        alternate_names=ALTERNATE_NAMES.get("openalex", None),
    ),
    OpenAlexIDField(
        param="openalex_id",
        alias="ids.openalex",
        custom_es_field="ids.openalex.lower",
        docstring=DOCSTRINGS["openalex"],
        documentation_link=DOCUMENTATION_LINKS["openalex"],
        alternate_names=ALTERNATE_NAMES.get("openalex", None),
    ),
    OpenAlexIDField(
        param="parent_publisher", custom_es_field="parent_publisher.id.keyword"
    ),
    OpenAlexIDField(param="roles.id"),
    RangeField(param="summary_stats.2yr_mean_citedness"),
    RangeField(param="cited_by_count"),
    RangeField(param="summary_stats.h_index"),
    RangeField(param="hierarchy_level"),
    RangeField(param="summary_stats.i10_index"),
    RangeField(param="works_count"),
    SearchField(param="default.search", index="publishers"),
    SearchField(
        param="display_name.search",
        docstring="Free text search among publishers' names",
        documentation_link="https://docs.openalex.org/api-entities/publishers/search-publishers#search-a-specific-field",
    ),
    TermField(param="country_codes", custom_es_field="country_codes.lower"),
    TermField(
        param=f"continent",
        custom_es_field="country_codes.lower",
    ),
    TermField(param="display_name", custom_es_field="display_name.keyword"),
    TermField(param="ids.ror", custom_es_field="ids.ror.lower"),
    TermField(
        param="ids.wikidata",
        custom_es_field="ids.wikidata.lower",
        unique_id="wikidata_entity",
    ),
    TermField(param="ror", custom_es_field="ids.ror.lower"),
    TermField(
        param="wikidata",
        custom_es_field="ids.wikidata.lower",
        unique_id="wikidata_entity",
    ),
]

fields_dict = {f.param: f for f in fields}
