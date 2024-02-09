from marshmallow import Schema, fields, post_dump

from core.schemas import (
    GroupBySchema,
    GroupBysSchema,
    MetaSchema,
    NumberIdSchema,
    hide_relevance,
    relevance_score,
)


class IDsSchema(Schema):
    openalex = fields.Str()
    wikipedia = fields.Str()

    class Meta:
        ordered = True


class TopicsSchema(Schema):
    id = fields.Str()
    display_name = fields.Str()
    description = fields.Str()
    keywords = fields.List(fields.Str())
    ids = fields.Nested(IDsSchema)
    subfield = fields.Nested(NumberIdSchema)
    field = fields.Nested(NumberIdSchema)
    domain = fields.Nested(NumberIdSchema)
    relevance_score = fields.Method("get_relevance_score")
    works_count = fields.Int()
    cited_by_count = fields.Int()
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
    results = fields.Nested(TopicsSchema, many=True)
    group_by = fields.Nested(GroupBySchema, many=True)
    group_bys = fields.Nested(GroupBysSchema, many=True)

    class Meta:
        ordered = True
