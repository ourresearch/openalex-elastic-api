from core.fields import (
    BooleanField,
    DateField,
    DateTimeField,
    OpenAlexIDField,
    RangeField,
    SearchField,
    TermField,
)

fields = [
    BooleanField(
        param="has_orcid",
        custom_es_field="ids.orcid",
        docstring="The author has an ORCID",
        documentation_link="https://docs.openalex.org/api-entities/authors/author-object#orcid",
    ),
    BooleanField(
        param=f"last_known_institution.is_global_south",
        custom_es_field="last_known_institution.country_code",
    ),
    DateField(
        param="from_created_date",
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
    OpenAlexIDField(param="concept.id", custom_es_field="x_concepts.id"),
    OpenAlexIDField(param="concepts.id", custom_es_field="x_concepts.id"),
    OpenAlexIDField(
        param="last_known_institution.id",
        docstring="The institution to which the author most recently claimed affiliation",
        documentation_link="https://docs.openalex.org/api-entities/authors/author-object#last_known_institution",
    ),
    OpenAlexIDField(
        param="last_known_institution.lineage",
        custom_es_field="last_known_institution.lineage",
    ),
    OpenAlexIDField(
        param="ids.openalex",
        docstring="The OpenAlex ID for the author",
        documentation_link="https://docs.openalex.org/how-to-use-the-api/get-single-entities#the-openalex-id",
    ),
    OpenAlexIDField(param="openalex", custom_es_field="ids.openalex.lower"),
    OpenAlexIDField(param="openalex_id", alias="ids.openalex"),
    OpenAlexIDField(
        param="x_concepts.id",
        docstring="Concepts that the author tends to publish about",
        documentation_link="https://docs.openalex.org/api-entities/concepts",
    ),
    RangeField(param="summary_stats.2yr_mean_citedness"),
    RangeField(param="cited_by_count"),
    RangeField(param="summary_stats.h_index"),
    RangeField(param="summary_stats.i10_index"),
    RangeField(param="works_count"),
    SearchField(param="default.search", index="authors"),
    SearchField(
        param="display_name.search",
        unique_id="author_search",
        docstring="Free text search among authors' names",
        documentation_link="https://docs.openalex.org/api-entities/authors/search-authors#search-a-specific-field",
    ),
    TermField(param="display_name", custom_es_field="display_name.keyword"),
    TermField(
        param="last_known_institution.country_code",
        docstring="The country of the author's last known institution",
        documentation_link="https://docs.openalex.org/api-entities/authors/author-object#last_known_institution",
    ),
    TermField(
        param="last_known_institution.continent",
        custom_es_field="last_known_institution.country_code",
    ),
    TermField(param="last_known_institution.ror"),
    TermField(
        param="last_known_institution.type",
        docstring="""The type of the author's last known institution. For example, universities are type "Education," and hospitals are type "Healthcare".""",
        documentation_link="https://docs.openalex.org/api-entities/institutions/institution-object#type",
    ),
    TermField(param="orcid", alias="ids.orcid"),
    TermField(param="scopus", alias="ids.scopus.keyword"),
]

fields_dict = {f.param: f for f in fields}
