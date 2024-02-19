from marshmallow import Schema, fields, post_dump

from core.schemas import (
    GroupBySchema,
    GroupBysSchema,
    MetaSchema,
    hide_relevance,
    relevance_score,
)


class ContinentSchema(Schema):
    id = fields.Str()
    display_name = fields.Str()

    class Meta:
        ordered = True


class IdsSchema(Schema):
    openalex = fields.Str()
    iso = fields.Str()
    wikidata = fields.Str()
    wikipedia = fields.Str()

    class Meta:
        ordered = True


class CountriesSchema(Schema):
    id = fields.Str()
    country_code = fields.Str()
    display_name = fields.Str()
    description = fields.Str()
    ids = fields.Nested(IdsSchema)
    display_name_alternatives = fields.List(fields.Str())
    relevance_score = fields.Method("get_relevance_score")
    continent = fields.Nested(ContinentSchema)
    is_global_south = fields.Bool()
    works_count = fields.Int()
    cited_by_count = fields.Int()
    authors_api_url = fields.Str()
    institutions_api_url = fields.Str()
    works_api_url = fields.Str()
    updated_date = fields.Str()
    created_date = fields.Str(dump_default=None)

    @post_dump
    def remove_relevance_score(self, data, many, **kwargs):
        return hide_relevance(data, self.context)

    @staticmethod
    def get_relevance_score(obj):
        return relevance_score(obj)

    class Meta:
        ordered = True


class MessageSchema(Schema):
    meta = fields.Nested(MetaSchema)
    results = fields.Nested(CountriesSchema, many=True)
    group_by = fields.Nested(GroupBySchema, many=True)
    group_bys = fields.Nested(GroupBysSchema, many=True)

    class Meta:
        ordered = True
