from marshmallow import INCLUDE, Schema, fields, post_dump

from core.schemas import (CountsByYearSchema, GroupBySchema, MetaSchema,
                          XConceptsSchema, hide_relevance, relevance_score)


class IDsSchema(Schema):
    openalex = fields.Str()
    issn_l = fields.Str()
    mag = fields.Str()
    issn = fields.List(fields.Str())

    class Meta:
        ordered = True
        unknown = INCLUDE


class VenuesSchema(Schema):
    id = fields.Str()
    issn_l = fields.Str()
    issn = fields.List(fields.Str())
    display_name = fields.Str()
    publisher = fields.Str()
    type = fields.Str()
    relevance_score = fields.Method("get_relevance_score")
    works_count = fields.Int()
    cited_by_count = fields.Int()
    is_oa = fields.Bool()
    is_in_doaj = fields.Bool()
    homepage_url = fields.Str()
    ids = fields.Nested(IDsSchema)
    x_concepts = fields.List(fields.Nested(XConceptsSchema))
    counts_by_year = fields.List(fields.Nested(CountsByYearSchema))
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
    results = fields.Nested(VenuesSchema, many=True)
    group_by = fields.Nested(GroupBySchema, many=True)

    class Meta:
        ordered = True
