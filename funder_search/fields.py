from core.fields import SearchField, TermField

fields = [
    SearchField(param="search", custom_es_field="html"),
    SearchField(param="default.search", index="funder-search"),
    TermField(param="doi", custom_es_field="doi"),
    TermField(param="fulltext_origin"),
]

fields_dict = {f.param: f for f in fields}