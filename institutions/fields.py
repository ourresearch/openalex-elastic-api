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
    "is_global_south": "The institution is located in the Global South. The Global South is a term used to identify regions within Latin America, Asia, Africa, and Oceania.",
    "openalex": "The OpenAlex ID for the institution",
    "concept": "Concepts that the institution's works tend to be about",
    "type": """The institution's type. For example, universities are type "Education," and hospitals are type "Healthcare".""",
}

# shared documentation_links for when multiple fields share the same link (such as aliases)
DOCUMENTATION_LINKS = {
    "is_global_south": "https://docs.openalex.org/api-entities/geo/regions",
    "openalex": "https://docs.openalex.org/how-to-use-the-api/get-single-entities#the-openalex-id",
    "concept": "https://docs.openalex.org/api-entities/concepts",
    "type": "https://docs.openalex.org/api-entities/institutions/institution-object#type",
}


fields = [
    BooleanField(
        param=f"is_global_south",
        custom_es_field="country_code",
        docstring=DOCSTRINGS["is_global_south"],
        documentation_link=DOCUMENTATION_LINKS["is_global_south"],
        alternate_names=ALTERNATE_NAMES.get("is_global_south", None),
    ),
    BooleanField(param="has_ror", custom_es_field="ids.ror.keyword"),
    DateField(
        param="from_created_date",
        custom_es_field="created_date",
    ),
    DateTimeField(
        param="from_updated_date",
        custom_es_field="updated_date",
    ),
    OpenAlexIDField(
        param="concept.id",
        custom_es_field="x_concepts.id",
        docstring=DOCSTRINGS["concept"],
        documentation_link=DOCUMENTATION_LINKS["concept"],
        alternate_names=ALTERNATE_NAMES.get("concept", None),
    ),
    OpenAlexIDField(param="concepts.id", custom_es_field="x_concepts.id",
                            docstring=DOCSTRINGS["concept"],
        documentation_link=DOCUMENTATION_LINKS["concept"],
        alternate_names=ALTERNATE_NAMES.get("concept", None),),
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
    OpenAlexIDField(param="roles.id"),
    OpenAlexIDField(param="lineage", custom_es_field="lineage"),
    OpenAlexIDField(
        param="repositories.host_organization",
        custom_es_field="repositories.host_organization",
    ),
    OpenAlexIDField(
        param="repositories.host_organization_lineage",
        alias="repositories.host_organization_lineage",
    ),
    OpenAlexIDField(param="repositories.id", custom_es_field="repositories.id"),
    OpenAlexIDField(
        param="x_concepts.id",
        docstring=DOCSTRINGS["concept"],
        documentation_link=DOCUMENTATION_LINKS["concept"],
        alternate_names=ALTERNATE_NAMES.get("concept", None),
    ),
    RangeField(param="summary_stats.2yr_mean_citedness"),
    RangeField(param="cited_by_count"),
    RangeField(param="summary_stats.h_index"),
    RangeField(param="summary_stats.i10_index"),
    RangeField(param="works_count"),
    SearchField(param="default.search", index="institutions"),
    SearchField(
        param="display_name.search",
        docstring="Free text search among institutions' names",
        documentation_link="https://docs.openalex.org/api-entities/institutions/search-institutions#search-a-specific-field",
    ),
    TermField(
        param="country_code",
        docstring="The country where the institution is located",
        documentation_link="https://docs.openalex.org/api-entities/institutions/institution-object#country_code",
        alternate_names=ALTERNATE_NAMES.get("country", None),
    ),
    TermField(
        param=f"continent",
        custom_es_field="country_code",
        docstring="The continent where the institution is located",
        documentation_link="https://docs.openalex.org/api-entities/geo/continents",
        alternate_names=ALTERNATE_NAMES.get("continent", None),
    ),
    TermField(param="display_name", custom_es_field="display_name.keyword"),
    TermField(param="ror", alias="ror"),
    TermField(
        param="type",
        docstring=DOCSTRINGS["type"],
        documentation_link=DOCUMENTATION_LINKS["type"],
        alternate_names=ALTERNATE_NAMES.get("institution.type", None),
    ),
]

fields_dict = {f.param: f for f in fields}
