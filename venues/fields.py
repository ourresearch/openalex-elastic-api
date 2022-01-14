from core.fields import (BooleanField, OpenAlexIDField, PhraseField,
                         RangeField, SearchField, TermField)

fields = [
    TermField(param="display_name"),
    SearchField(param="display_name.search"),
    RangeField(param="cited_by_count"),
    BooleanField(param="is_in_doaj"),
    BooleanField(param="is_oa"),
    TermField(param="issn", custom_es_field="issn__lower"),
    PhraseField(param="publisher", custom_es_field="publisher__lower"),
    RangeField(param="works_count"),
    OpenAlexIDField(param="x_concepts.id", custom_es_field="x_concepts__id__lower"),
]

fields_dict = {f.param: f for f in fields}
