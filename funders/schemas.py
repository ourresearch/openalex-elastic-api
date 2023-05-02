from marshmallow import INCLUDE, Schema, fields, post_dump

from core.schemas import (CountsByYearSchema, GroupBySchema, MetaSchema,
                          RolesSchema, SummaryStatsSchema, hide_relevance,
                          relevance_score)


class IDsSchema(Schema):
    openalex = fields.Str()
    ror = fields.Str()
    wikidata = fields.Str()

    class Meta:
        ordered = True
        unknown = INCLUDE


class FundersSchema(Schema):
    id = fields.Str()
    display_name = fields.Str()
    alternate_titles = fields.List(fields.Str())
    country_code = fields.Str(dump_default=None)
    description = fields.Str(dump_default=None)
    homepage_url = fields.Str(dump_default=None)
    image_url = fields.Str(dump_default=None)
    image_thumbnail_url = fields.Str(dump_default=None)
    relevance_score = fields.Method("get_relevance_score")
    works_count = fields.Int()
    cited_by_count = fields.Int()
    summary_stats = fields.Nested(SummaryStatsSchema, dump_default=None)
    ids = fields.Nested(IDsSchema)
    counts_by_year = fields.List(fields.Nested(CountsByYearSchema))
    roles = fields.List(fields.Nested(RolesSchema))
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
    results = fields.Nested(FundersSchema, many=True)
    group_by = fields.Nested(GroupBySchema, many=True)

    class Meta:
        ordered = True
