from core.fields import (BooleanField, OpenAlexIDField, PhraseField,
                         RangeField, SearchField, TermField)

fields = [
    BooleanField(param="is_in_doaj"),
    BooleanField(param="is_oa"),
    OpenAlexIDField(param="x_concepts.id"),
    PhraseField(param="publisher"),
    RangeField(param="cited_by_count"),
    RangeField(param="works_count"),
    SearchField(param="display_name.search"),
    TermField(param="display_name"),
    TermField(param="issn"),
]

fields_dict = {f.param: f for f in fields}
