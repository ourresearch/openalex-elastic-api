from marshmallow import Schema, fields, post_dump

from core.schemas import (
    GroupBySchema,
    GroupBysSchema,
    MetaSchema,
    hide_relevance,
    relevance_score,
)


class CountrySchema(Schema):
    id = fields.Str()
    display_name = fields.Str()

    class Meta:
        ordered = True


class IdsSchema(Schema):
    openalex = fields.Str()
    wikidata = fields.Str()
    wikipedia = fields.Str()

    class Meta:
        ordered = True


class ContinentsSchema(Schema):
    id = fields.Str()
    display_name = fields.Str()
    description = fields.Str()
    ids = fields.Nested(IdsSchema)
    display_name_alternatives = fields.List(fields.Str())
    countries = fields.Nested(CountrySchema, many=True)
    relevance_score = fields.Method("get_relevance_score")
    works_count = fields.Int()
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
    results = fields.Nested(ContinentsSchema, many=True)
    group_by = fields.Nested(GroupBySchema, many=True)
    group_bys = fields.Nested(GroupBysSchema, many=True)

    class Meta:
        ordered = True
