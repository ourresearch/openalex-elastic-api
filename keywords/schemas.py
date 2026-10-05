from marshmallow import fields, Schema, post_dump

from core.schemas import (
    GroupBySchema,
    GroupBysSchema,
    MetaSchema,
    TopicSchema,
    hide_relevance,
    relevance_score,
)


class IDsSchema(Schema):
    openalex = fields.Str()
    wikidata = fields.Str()

    class Meta:
        ordered = True


class KeywordsSchema(Schema):
    id = fields.Str()
    display_name = fields.Str()
    description = fields.Str()
    display_name_alternatives = fields.List(fields.Str())
    ids = fields.Nested(IDsSchema)
    # oxjob #1307: score = share of the keyword's works in the topic; topics holds every link with score >= 0.07,
    # best first; primary_topic is the top link when its score >= 0.2, else null (a broad keyword)
    primary_topic = fields.Nested(TopicSchema, allow_none=True, dump_default=None)
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
    results = fields.Nested(KeywordsSchema, many=True)
    group_by = fields.Nested(GroupBySchema, many=True)
    group_bys = fields.Nested(GroupBysSchema, many=True)

    class Meta:
        ordered = True
