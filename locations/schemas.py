from marshmallow import INCLUDE, Schema, fields, post_dump

from core.schemas import (
    GroupBySchema,
    GroupBysSchema,
    MetaSchema,
    hide_relevance,
    relevance_score,
)


class LocationsSchema(Schema):
    id = fields.Str()
    work_id = fields.Str()
    native_id = fields.Str()
    native_id_namespace = fields.Str()
    title = fields.Str()
    type = fields.Str()
    source_name = fields.Str()
    publisher = fields.Str()
    source_id = fields.Str()
    is_oa = fields.Bool()
    version = fields.Str()
    license = fields.Str()
    language = fields.Str()
    is_retracted = fields.Bool()
    landing_page_url = fields.Str()
    pdf_url = fields.Str()
    relevance_score = fields.Method("get_relevance_score")

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
    results = fields.Nested(LocationsSchema, many=True)
    group_by = fields.Nested(GroupBySchema, many=True)
    group_bys = fields.Nested(GroupBysSchema, many=True)

    class Meta:
        ordered = True