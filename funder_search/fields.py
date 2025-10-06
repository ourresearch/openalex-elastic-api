from core.fields import SearchField, TermField, OpenAlexIDField

fields = [
    SearchField(param="search", custom_es_field="html"),
    SearchField(param="fulltext.search", custom_es_field="fulltext"),
    SearchField(param="default.search", index="funder-search"),
    TermField(param="doi", custom_es_field="doi"),
    TermField(param="search_type", custom_es_field="search_type"),
]

fields_dict = {f.param: f for f in fields}