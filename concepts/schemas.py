from collections import OrderedDict

from marshmallow import INCLUDE, Schema, fields, post_dump

from core.schemas import (CountsByYearSchema, GroupBySchema, GroupBysSchema,
                          MetaSchema, SummaryStatsSchema, hide_relevance,
                          relevance_score)


class IDsSchema(Schema):
    openalex = fields.Str()
    wikidata = fields.Str()
    mag = fields.Str()
    wikipedia = fields.Str()
    umls_aui = fields.List(fields.Str())
    umls_cui = fields.List(fields.Str())

    class Meta:
        ordered = True
        unknown = INCLUDE


class AncestorsSchema(Schema):
    id = fields.Str()
    wikidata = fields.Str()
    display_name = fields.Str()
    level = fields.Int()

    class Meta:
        ordered = True


class RelatedConceptsSchema(Schema):
    id = fields.Str()
    wikidata = fields.Str()
    display_name = fields.Str()
    level = fields.Int()
    score = fields.Float()

    class Meta:
        ordered = True


class ConceptsSchema(Schema):
    id = fields.Str()
    wikidata = fields.Str()
    display_name = fields.Str()
    relevance_score = fields.Method("get_relevance_score")
    level = fields.Int()
    description = fields.Str()
    works_count = fields.Int()
    cited_by_count = fields.Int()
    summary_stats = fields.Nested(SummaryStatsSchema, dump_default=None)
    ids = fields.Nested(IDsSchema)
    image_url = fields.Str()
    image_thumbnail_url = fields.Str()
    international = fields.Method("get_international")
    ancestors = fields.List(fields.Nested(AncestorsSchema))
    related_concepts = fields.List(fields.Nested(RelatedConceptsSchema))
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

    def get_international(self, obj):
        """Returns international field sorted as display_name, description."""
        sorted_dict = OrderedDict()
        if obj and "international" in obj and obj.international:
            international = obj.international.to_dict()
            display_names = international.get("display_name")
            descriptions = international.get("description")
            sorted_dict["display_name"] = (
                dict(sorted(display_names.items())) if display_names else None
            )
            sorted_dict["description"] = (
                dict(sorted(descriptions.items())) if descriptions else None
            )
        return sorted_dict

    class Meta:
        ordered = True


class MessageSchema(Schema):
    meta = fields.Nested(MetaSchema)
    results = fields.Nested(ConceptsSchema, many=True)
    group_by = fields.Nested(GroupBySchema, many=True)
    group_bys = fields.Nested(GroupBysSchema, many=True)

    class Meta:
        ordered = True
