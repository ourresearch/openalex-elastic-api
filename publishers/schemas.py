from marshmallow import INCLUDE, Schema, fields, post_dump

from core.schemas import (
    CountsByYearSchema,
    GroupBySchema,
    MetaSchema,
    SummaryStatsSchema,
    RolesSchema,
    hide_relevance,
    relevance_score,
)


class IDsSchema(Schema):
    openalex = fields.Str()
    ror = fields.Str()
    wikidata = fields.Str()

    class Meta:
        ordered = True
        unknown = INCLUDE


class PublishersSchema(Schema):
    id = fields.Str()
    display_name = fields.Str()
    alternate_titles = fields.List(fields.Str())
    hierarchy_level = fields.Int()
    parent_publisher = fields.Str()
    lineage = fields.List(fields.Str())
    relevance_score = fields.Method("get_relevance_score")
    country_codes = fields.List(fields.Str())
    image_url = fields.Str(dump_default=None)
    image_thumbnail_url = fields.Str(dump_default=None)
    works_count = fields.Int()
    cited_by_count = fields.Int()
    summary_stats = fields.Nested(SummaryStatsSchema, dump_default=None)
    ids = fields.Nested(IDsSchema)
    counts_by_year = fields.List(fields.Nested(CountsByYearSchema))
    roles = fields.List(fields.Nested(RolesSchema))
    sources_api_url = fields.Str()
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
    results = fields.Nested(PublishersSchema, many=True)
    group_by = fields.Nested(GroupBySchema, many=True)

    class Meta:
        ordered = True
