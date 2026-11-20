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
    credit = fields.Str()

    class Meta:
        ordered = True


class ContributorRolesSchema(Schema):
    """One of the 14 CRediT roles (oxjob #2075). `works_count` = works where at least one
    author carries the role. No works_api_url: there is no works filter on a role alone (the
    filter that ships pairs an author with a role)."""

    id = fields.Str()
    display_name = fields.Str()
    description = fields.Str()
    ids = fields.Nested(IdsSchema)
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
    results = fields.Nested(ContributorRolesSchema, many=True)
    group_by = fields.Nested(GroupBySchema, many=True)
    group_bys = fields.Nested(GroupBysSchema, many=True)

    class Meta:
        ordered = True
