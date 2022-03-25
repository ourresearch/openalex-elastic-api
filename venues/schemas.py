from marshmallow import INCLUDE, Schema, fields, post_dump

from core.schemas import (CountsByYearSchema, GroupBySchema, MetaSchema,
                          XConceptsSchema)


class IDsSchema(Schema):
    openalex = fields.Str()
    issn = fields.List(fields.Str())
    issn_l = fields.Str()
    mag = fields.Str()

    class Meta:
        ordered = True
        unknown = INCLUDE


class VenuesSchema(Schema):
    id = fields.Str()
    display_name = fields.Str()
    publisher = fields.Str()
    issn_l = fields.Str()
    issn = fields.List(fields.Str())
    relevance_score = fields.Method("get_relevance_score")
    works_count = fields.Int()
    cited_by_count = fields.Int()
    is_oa = fields.Bool()
    is_in_doaj = fields.Bool()
    homepage_url = fields.Str()
    ids = fields.Nested(IDsSchema)
    counts_by_year = fields.List(fields.Nested(CountsByYearSchema))
    x_concepts = fields.List(fields.Nested(XConceptsSchema))
    works_api_url = fields.Str()
    updated_date = fields.Str()
    created_date = fields.Str(default=None)

    @post_dump
    def remove_relevance_score(self, data, many, **kwargs):
        if (
            not data["relevance_score"]
            or "display_relevance" in self.context
            and self.context["display_relevance"] is False
        ):
            del data["relevance_score"]
        return data

    def get_relevance_score(self, obj):
        if obj.meta.score and obj.meta != 0.0:
            return obj.meta.score

    class Meta:
        ordered = True


class MessageSchema(Schema):
    meta = fields.Nested(MetaSchema)
    results = fields.Nested(VenuesSchema, many=True)
    group_by = fields.Nested(GroupBySchema, many=True)

    class Meta:
        ordered = True
