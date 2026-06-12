from core.fields import (
    BooleanField,
    DateField,
    DateTimeField,
    CollectionField,
    OpenAlexIDField,
    PhraseField,
    RangeField,
    SearchField,
    TermField,
    annotate_entity_types,
)
from core.alternate_names import ALTERNATE_NAMES

# shared docstrings for when multiple fields share the same docstring (such as aliases)
DOCSTRINGS = {
    "openalex": "The OpenAlex ID for the source",
    "concept": "Concepts that the source's works tend to be about",
    "type": "The source type, such as journal or repository",
}

# shared documentation_links for when multiple fields share the same link (such as aliases)
DOCUMENTATION_LINKS = {
    "openalex": "https://developers.openalex.org/guides/get",
    "concept": "https://developers.openalex.org/api-reference/concepts",
    "type": "https://developers.openalex.org/api-reference/sources",
}

fields = [
    BooleanField(param="has_issn", custom_es_field="ids.issn_l"),
    BooleanField(
        param="is_in_doaj",
        docstring="The journal is in DOAJ, the Directory of Open Access Journals",
        documentation_link="https://developers.openalex.org/api-reference/sources",
        alternate_names=ALTERNATE_NAMES.get("source.is_in_doaj", None),
    ),
    BooleanField(
        param="is_oa",
        docstring="The source is currently Open Access",
        documentation_link="https://developers.openalex.org/api-reference/sources",
        alternate_names=ALTERNATE_NAMES.get("is_oa", None),
    ),
    BooleanField(
        param="is_core",
    ),
    BooleanField(
        param="is_ojs",
    ),
    BooleanField(
        param=f"is_global_south",
        custom_es_field="country_code",
    ),
    BooleanField(
        param="is_high_oa_rate",
        docstring="The source has a high Open Access rate",
    ),
    BooleanField(
        param="is_in_jstage",
        docstring="The source is in J-STAGE, the Japan Science and Technology Information Aggregation Service",
    ),
    DateField(
        param="from_created_date",
        custom_es_field="created_date",
    ),
    DateField(
        param="to_created_date",
        custom_es_field="created_date",
    ),
    DateTimeField(
        param="from_updated_date",
        custom_es_field="updated_date",
    ),
    DateTimeField(
        param="to_updated_date",
        custom_es_field="updated_date",
    ),
    OpenAlexIDField(
        param="concept.id",
        custom_es_field="x_concepts.id",
        docstring=DOCSTRINGS["concept"],
        documentation_link=DOCUMENTATION_LINKS["concept"],
        alternate_names=ALTERNATE_NAMES.get("concept", None),
        alternate_of="x_concepts.id",
    ),
    OpenAlexIDField(
        param="concepts.id",
        custom_es_field="x_concepts.id",
        docstring=DOCSTRINGS["concept"],
        documentation_link=DOCUMENTATION_LINKS["concept"],
        alternate_names=ALTERNATE_NAMES.get("concept", None),
        alternate_of="x_concepts.id",
    ),
    OpenAlexIDField(param="host_organization"),
    OpenAlexIDField(
        param="host_organization.id", custom_es_field="host_organization.lower"
    ),
    OpenAlexIDField(param="host_organization_lineage"),
    OpenAlexIDField(
        param="ids.openalex",
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
    OpenAlexIDField(
        param="x_concepts.id",
        docstring=DOCSTRINGS["concept"],
        documentation_link=DOCUMENTATION_LINKS["concept"],
        alternate_names=ALTERNATE_NAMES.get("concept", None),
    ),
    RangeField(param="apc_usd"),
    RangeField(param="apc_prices.price"),
    RangeField(param="cited_by_count"),
    RangeField(param="is_in_doaj_since_year"),
    RangeField(param="is_high_oa_rate_since_year"),
    RangeField(param="is_in_jstage_since_year"),
    RangeField(param="last_publication_year"),
    RangeField(param="first_publication_year"),
    RangeField(param="oa_flip_year"),
    RangeField(param="summary_stats.2yr_mean_citedness"),
    RangeField(param="summary_stats.h_index"),
    RangeField(param="summary_stats.i10_index"),
    RangeField(param="works_count"),
    SearchField(param="default.search", index="sources"),
    SearchField(
        param="display_name.search",
        docstring="Free text search among sources' names",
        documentation_link="https://developers.openalex.org/guides/searching",
    ),
    TermField(
        param="apc_prices.currency",
    ),
    TermField(
        param=f"continent",
        custom_es_field="country_code",
    ),
    TermField(param="country_code"),
    TermField(param="display_name", custom_es_field="display_name.keyword"),
    TermField(param="ids.mag", custom_es_field="ids.mag"),
    TermField(param="issn"),
    TermField(param="issn_l", custom_es_field="issn_l"),
    TermField(param="topics.id"),
    TermField(param="topic_share.id", custom_es_field="topic_share.id.keyword"),
    TermField(
        param="type",
        # #394: collectible as a `source-types` collection. Bare `type` is
        # polysemous across endpoints, so entity_type is set directly here
        # rather than via the global ENTITY_ID_PARAM_TYPES dict.
        entity_type="source-types",
        docstring=DOCSTRINGS["type"],
        documentation_link=DOCUMENTATION_LINKS["type"],
        alternate_names=ALTERNATE_NAMES.get("source.type", None),
    ),
    CollectionField(entity_type="sources"),
]

# Cross-type collection filter (#266): annotate fields with unambiguous entity-ID
# semantics. The canonical id-shaped params on /sources resolve to sources.
annotate_entity_types(fields)
for f in fields:
    if f.param in ("id", "ids.openalex", "openalex", "openalex_id") and f.entity_type is None:
        f.entity_type = "sources"

fields_dict = {f.param: f for f in fields}
