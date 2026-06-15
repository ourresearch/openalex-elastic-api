from core.fields import SearchField, TermField

fields = [
    SearchField(param="search", custom_es_field="html"),
    SearchField(param="text.search", index="funder-search"),
    SearchField(param="default.search", index="funder-search", alternate_of="text.search"),
    TermField(param="doi", custom_es_field="doi"),
    TermField(param="fulltext_origin"),
]

fields_dict = {f.param: f for f in fields}