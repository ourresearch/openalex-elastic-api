from marshmallow import Schema, fields, post_dump

from core.schemas import (
    GroupBySchema,
    GroupBysSchema,
    MetaSchema,
    hide_relevance,
    relevance_score,
)


class IdsSchema(Schema):
    openalex = fields.Str()
    un = fields.Str()
    wikidata = fields.Str()

    class Meta:
        ordered = True

class SdgsSchema(Schema):
    id = fields.Str()
    display_name = fields.Str()
    relevance_score = fields.Method("get_relevance_score")
    description = fields.Str()
    ids = fields.Nested(IdsSchema)
    works_count = fields.Int()
    cited_by_count = fields.Int()
    image_url = fields.Str()
    image_thumbnail_url = fields.Str()
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
    results = fields.Nested(SdgsSchema, many=True)
    group_by = fields.Nested(GroupBySchema, many=True)
    group_bys = fields.Nested(GroupBysSchema, many=True)

    class Meta:
        ordered = True
