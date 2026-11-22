from marshmallow import Schema, fields, post_dump

from core.schemas import (
    GroupBySchema,
    GroupBysSchema,
    MetaSchema,
    hide_relevance,
    relevance_score,
)


class StandardTermSchema(Schema):
    """The same link in a standard vocabulary (oxjob #1490): Dublin Core, schema.org, DataCite, Crossref, DCAT.
    `match` (oxjob #2264) is how close their term is to ours, as a SKOS mapping level: exact, close, broad, narrow or
    related. Served as the index holds it; null on a record written before walden filled it."""

    vocabulary = fields.Str()
    term = fields.Str()
    url = fields.Str()
    match = fields.Str(dump_default=None)

    class Meta:
        ordered = True


class RelationshipsSchema(Schema):
    """One kind of link between two works: citation (oxjob #1490), or a part-of kind (oxjob #2065): volume,
    component, data-series, part. `works_count` = works that carry a link of this kind.
    Values are nouns that name the link, not one end of it; `standard_terms` gives the
    matching verbs in standard vocabularies (Jason, 15 Nov 2026, oxjob #1490)."""

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
    results = fields.Nested(RelationshipsSchema, many=True)
    group_by = fields.Nested(GroupBySchema, many=True)
    group_bys = fields.Nested(GroupBysSchema, many=True)

    class Meta:
        ordered = True
