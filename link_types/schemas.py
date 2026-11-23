from marshmallow import Schema, fields, post_dump

from core.schemas import (
    GroupBySchema,
    GroupBysSchema,
    MetaSchema,
    hide_relevance,
    relevance_score,
)
from relationships.schemas import LinkStandardTermSchema


class LinkTypesSchema(Schema):
    """One kind of link between two works (oxjob #2481): citation, review, or a part-of kind (volume, component,
    data-series, part). The /relationships record under its new name: same fields, ids
    https://openalex.org/link-types/<slug>. `works_count` = works that carry a link of this kind."""

    id = fields.Str()
    display_name = fields.Str()
    description = fields.Str()
    standard_terms = fields.List(fields.Nested(LinkStandardTermSchema))
    relevance_score = fields.Method("get_relevance_score")
    works_count = fields.Int()
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
    results = fields.Nested(LinkTypesSchema, many=True)
    group_by = fields.Nested(GroupBySchema, many=True)
    group_bys = fields.Nested(GroupBysSchema, many=True)

    class Meta:
        ordered = True
