from marshmallow import Schema, fields, post_dump

from core.schemas import (
    GroupBySchema,
    GroupBysSchema,
    MetaSchema,
    hide_relevance,
    relevance_score,
)


class StandardTermSchema(Schema):
    """The same kind of agent in a standard vocabulary (W3C PROV-O, schema.org, Wikidata, ...)."""

    vocabulary = fields.Str()
    term = fields.Str()
    url = fields.Str()

    class Meta:
        ordered = True


class AuthorTypesSchema(Schema):
    """What kind of agent an author is (oxjob #2437): human, organization or software-agent. Named in our
    words; `standard_terms` lists the matching class in standard vocabularies, as /relationships does.
    `works_count` = works with at least one author of this type."""

    id = fields.Str()
    display_name = fields.Str()
    description = fields.Str()
    standard_terms = fields.List(fields.Nested(StandardTermSchema))
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
    results = fields.Nested(AuthorTypesSchema, many=True)
    group_by = fields.Nested(GroupBySchema, many=True)
    group_bys = fields.Nested(GroupBysSchema, many=True)

    class Meta:
        ordered = True
