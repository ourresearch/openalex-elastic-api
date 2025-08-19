from marshmallow import INCLUDE, Schema, fields, post_dump

from core.schemas import (
    GroupBySchema,
    GroupBysSchema,
    MetaSchema,
    hide_relevance,
    relevance_score,
)

class MergeKeySchema(Schema):
    doi = fields.Str(default=None)
    arxiv = fields.Str(default=None)
    pmid = fields.Str(default=None)
    title_author = fields.Str(default=None)

    class Meta:
        ordered = True
        unknown = INCLUDE


class IdsSchema(Schema):
    id = fields.Str()
    namespace = fields.Str()
    relationship = fields.Str(default=None)

    class Meta:
        ordered = True
        unknown = INCLUDE


class UrlsSchema(Schema):
    url = fields.Str()
    content_type = fields.Str(default=None)


class LocationsSchema(Schema):
    id = fields.Str()
    work_id = fields.Str()
    native_id = fields.Str()
    native_id_namespace = fields.Str()
    provenance = fields.Str(default=None)
    title = fields.Str()
    type = fields.Str()
    source_name = fields.Str(default=None)
    publisher = fields.Str(default=None)
    source_id = fields.Str(default=None)
    is_oa = fields.Bool()
    version = fields.Str(default=None)
    license = fields.Str(default=None)
    language = fields.Str(default=None)
    is_retracted = fields.Bool(defaul=False)
    landing_page_url = fields.Str(default=None)
    pdf_url = fields.Str(default=None)
    ids = fields.Nested(IdsSchema, many=True, default=None)
    urls = fields.Nested(UrlsSchema, many=True, default=None)
    merge_key = fields.Nested(MergeKeySchema, default=None)
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