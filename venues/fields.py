from core.fields import (BooleanField, DateField, OpenAlexIDField, PhraseField,
                         RangeField, SearchField, TermField)

fields = [
    BooleanField(param="has_issn", custom_es_field="ids.issn_l"),
    BooleanField(param="is_in_doaj"),
    BooleanField(param="is_oa"),
    DateField(
        param="from_created_date",
        custom_es_field="created_date",
    ),
    DateField(
        param="from_updated_date",
        custom_es_field="updated_date",
    ),
    OpenAlexIDField(param="x_concepts.id"),
    PhraseField(param="publisher"),
    RangeField(param="cited_by_count"),
    RangeField(param="works_count"),
    SearchField(param="display_name.search"),
    TermField(param="display_name", custom_es_field="display_name.keyword"),
    TermField(param="issn"),
    TermField(param="openalex_id", alias="ids.openalex"),
]

fields_dict = {f.param: f for f in fields}
