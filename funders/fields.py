from core.fields import (
    BooleanField,
    DateField,
    DateTimeField,
    CollectionField,
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
    "openalex": "https://developers.openalex.org/guides/get",
}

fields = [
    BooleanField(
        param=f"is_global_south",
        custom_es_field="country_code",
    ),
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
    # OpenAlexIDField(
    #     param="ids.openalex",
    #     docstring=DOCSTRINGS["openalex"],
    #     documentation_link=DOCUMENTATION_LINKS["openalex"],
    #     alternate_names=ALTERNATE_NAMES.get("openalex", None),
    # ),
    OpenAlexIDField(
        param="openalex",
        custom_es_field="ids.openalex.lower",
        docstring=DOCSTRINGS["openalex"],
        documentation_link=DOCUMENTATION_LINKS["openalex"],
        alternate_names=ALTERNATE_NAMES.get("openalex", None),
        alternate_of="ids.openalex",
    ),
    OpenAlexIDField(
        param="openalex_id",
        alias="ids.openalex",
        docstring=DOCSTRINGS["openalex"],
        documentation_link=DOCUMENTATION_LINKS["openalex"],
        alternate_names=ALTERNATE_NAMES.get("openalex", None),
        alternate_of="ids.openalex",
    ),
    OpenAlexIDField(param="roles.id"),
    RangeField(param="summary_stats.2yr_mean_citedness"),
    RangeField(param="cited_by_count"),
    RangeField(param="awards_count"),
    RangeField(param="summary_stats.h_index"),
    RangeField(param="summary_stats.i10_index"),
    RangeField(param="works_count"),
    SearchField(param="text.search", index="funders"),
    SearchField(param="default.search", index="funders", alternate_of="text.search"),
    SearchField(param="description.search", custom_es_field="description"),
    SearchField(
        param="display_name.search",
        docstring="Free text search among funders' names",
        documentation_link="https://developers.openalex.org/guides/searching",
    ),
    TermField(
        param=f"continent",
        custom_es_field="country_code",
    ),
    TermField(param="country_code"),
    TermField(param="display_name", custom_es_field="display_name.keyword"),
    TermField(param="ids.ror", custom_es_field="ids.ror.lower"),
    TermField(
        param="ids.wikidata",
        custom_es_field="ids.wikidata.lower",
        unique_id="wikidata_entity",
    ),
    TermField(
        param="ror", custom_es_field="ids.ror.lower", alternate_of="ids.ror"
    ),
    TermField(
        param="wikidata",
        custom_es_field="ids.wikidata.lower",
        unique_id="wikidata_entity",
        alternate_of="ids.wikidata",
    ),
    TermField(param="ids.crossref", custom_es_field="ids.crossref"),
    TermField(param="ids.doi", custom_es_field="ids.doi.keyword"),
    CollectionField(entity_type="funders"),
]

fields_dict = {f.param: f for f in fields}
