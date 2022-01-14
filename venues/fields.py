from core.fields import (BooleanField, OpenAlexIDField, PhraseField,
                         RangeField, SearchField, TermField)

fields = [
    TermField(param="display_name"),
    SearchField(param="display_name.search"),
    RangeField(param="cited_by_count"),
    BooleanField(param="is_in_doaj"),
    BooleanField(param="is_oa"),
    TermField(param="issn"),
    PhraseField(param="publisher"),
    RangeField(param="works_count"),
    OpenAlexIDField(param="x_concepts.id"),
]

fields_dict = {f.param: f for f in fields}
