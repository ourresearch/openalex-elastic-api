import re
from marshmallow import INCLUDE, Schema, fields, post_dump

from core.schemas import MetaSchema, hide_relevance, relevance_score


class FunderSearchSchema(Schema):
    id = fields.Str()
    doi = fields.Str()
    snippets = fields.Method("get_snippet")
    relevance_score = fields.Method("get_relevance_score")

    @staticmethod
    def get_snippet(obj):
        if not hasattr(obj.meta, 'highlight') or 'fulltext' not in obj.meta.highlight:
            return None

        # Fulltext is already clean text, just return the highlights
        return list(obj.meta.highlight.fulltext)

    @post_dump
    def remove_relevance_score(self, data, many, **kwargs):
        return hide_relevance(data, self.context)

    @staticmethod
    def get_relevance_score(obj):
        return relevance_score(obj)

    class Meta:
        ordered = True
        unknown = INCLUDE


class MessageSchema(Schema):
    meta = fields.Nested(MetaSchema)
    results = fields.Nested(FunderSearchSchema, many=True)

    class Meta:
        ordered = True