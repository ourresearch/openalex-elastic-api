from marshmallow import INCLUDE, Schema, fields

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
    relevance_score = fields.Float(attribute="meta.score")
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

    class Meta:
        ordered = True


class MessageSchema(Schema):
    meta = fields.Nested(MetaSchema)
    results = fields.Nested(VenuesSchema, many=True)
    group_by = fields.Nested(GroupBySchema, many=True)

    class Meta:
        ordered = True
