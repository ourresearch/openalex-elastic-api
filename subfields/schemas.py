from marshmallow import fields, Schema, post_dump

from core.schemas import (
    GroupBySchema,
    GroupBysSchema,
    MetaSchema,
    NumberIdSchema,
    hide_relevance,
    relevance_score,
)


class TopicSchema(Schema):
    id = fields.Str()
    display_name = fields.Str()


class IdsSchema(Schema):
    openalex = fields.Str()
    wikidata = fields.Str()
    wikipedia = fields.Str()

    class Meta:
        ordered = True



class SubfieldsSchema(Schema):
    id = fields.Int()
    display_name = fields.Str()
    description = fields.Str()
    ids = fields.Nested(IdsSchema)
    display_name_alternatives = fields.List(fields.Str())
    field = fields.Nested(NumberIdSchema)
    domain = fields.Nested(NumberIdSchema)
    topics = fields.Nested(TopicSchema, many=True)
    relevance_score = fields.Method("get_relevance_score")
    works_count = fields.Int()
    cited_by_count = fields.Int()
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
    results = fields.Nested(SubfieldsSchema, many=True)
    group_by = fields.Nested(GroupBySchema, many=True)
    group_bys = fields.Nested(GroupBysSchema, many=True)

    class Meta:
        ordered = True
