from core.fields import (BooleanField, DateField, DateTimeField,
                         OpenAlexIDField, RangeField, SearchField, TermField)

fields = [
    BooleanField(param="has_orcid", custom_es_field="ids.orcid"),
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
    OpenAlexIDField(param="concept.id", custom_es_field="x_concepts.id"),
    OpenAlexIDField(param="concepts.id", custom_es_field="x_concepts.id"),
    OpenAlexIDField(param="last_known_institution.id"),
    OpenAlexIDField(param="openalex", custom_es_field="ids.openalex.lower"),
    OpenAlexIDField(param="openalex_id", alias="ids.openalex"),
    OpenAlexIDField(param="x_concepts.id"),
    RangeField(param="summary_stats.2yr_mean_citedness"),
    RangeField(param="cited_by_count"),
    RangeField(param="summary_stats.h_index"),
    RangeField(param="summary_stats.i10_index"),
    RangeField(param="works_count"),
    SearchField(param="display_name.search", unique_id="author_search"),
    TermField(param="display_name", custom_es_field="display_name.keyword"),
    TermField(param="last_known_institution.country_code"),
    TermField(
        param="last_known_institution.continent",
        custom_es_field="last_known_institution.country_code",
    ),
    TermField(param="last_known_institution.ror"),
    TermField(param="last_known_institution.type"),
    TermField(param="orcid", alias="ids.orcid"),
]

fields_dict = {f.param: f for f in fields}
