from marshmallow import Schema, fields, post_dump

from core.schemas import (
    GroupBySchema,
    GroupBysSchema,
    MetaSchema,
    TopicHierarchySchema,
    hide_relevance,
    relevance_score,
)


class IDsSchema(Schema):
    openalex = fields.Str()
    wikipedia = fields.Str()

    class Meta:
        ordered = True


class TopicKeywordSchema(Schema):
    id = fields.Str()
    display_name = fields.Str()
    score = fields.Float()

    class Meta:
        ordered = True


class TopicsSchema(Schema):
    id = fields.Str()
    display_name = fields.Str()
    description = fields.Str()
    # oxjob #1307: the topic's top 25 keywords by how many of its works carry them; score = the keyword's share
    # of works in this topic. The full list: /keywords?filter=topics.id:T...
    keywords = fields.Nested(TopicKeywordSchema, many=True)
    # the 10 keyword strings topics shipped with (CWTS), one "; "-delimited string
    legacy_keywords = fields.Str()
    ids = fields.Nested(IDsSchema)
    subfield = fields.Nested(TopicHierarchySchema)
    field = fields.Nested(TopicHierarchySchema)
    domain = fields.Nested(TopicHierarchySchema)
    siblings = fields.Nested(TopicHierarchySchema, many=True)
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
    results = fields.Nested(TopicsSchema, many=True)
    group_by = fields.Nested(GroupBySchema, many=True)
    group_bys = fields.Nested(GroupBysSchema, many=True)

    class Meta:
        ordered = True
