from collections import OrderedDict

from marshmallow import INCLUDE, Schema, fields, post_dump

from core.schemas import CountsByYearSchema, GroupBySchema, MetaSchema


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
        if (
            not data["relevance_score"]
            and data["relevance_score"] != 0
            or "display_relevance" in self.context
            and self.context["display_relevance"] is False
        ):
            del data["relevance_score"]
        return data

    def get_relevance_score(self, obj):
        if obj.meta.score and obj.meta != 0.0:
            return obj.meta.score

    def get_international(self, obj):
        """Returns international field sorted as display_name, description."""
        sorted_dict = OrderedDict()
        if obj and "international" in obj:
            international = obj.international.to_dict()
            sorted_dict["display_name"] = international.get("display_name")
            sorted_dict["description"] = international.get("description")
        return sorted_dict

    class Meta:
        ordered = True


class MessageSchema(Schema):
    meta = fields.Nested(MetaSchema)
    results = fields.Nested(ConceptsSchema, many=True)
    group_by = fields.Nested(GroupBySchema, many=True)

    class Meta:
        ordered = True
