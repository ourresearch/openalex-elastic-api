from marshmallow import INCLUDE, Schema, fields

from core.schemas import CountsByYearSchema, GroupBySchema, MetaSchema


class IDsSchema(Schema):
    openalex = fields.Str()
    wikidata = fields.Str()
    wikipedia = fields.Str()
    umls_aui = fields.List(fields.Str())
    umls_cui = fields.List(fields.Str())
    mag = fields.Str()

    class Meta:
        ordered = True
        unknown = INCLUDE


class AncestorsSchema(Schema):
    id = fields.Str()
    wikidata = fields.Str()
    display_name = fields.Str()
    level = fields.Int()


class RelatedConceptsSchema(Schema):
    id = fields.Str()
    wikidata = fields.Str()
    display_name = fields.Str()
    level = fields.Int()
    score = fields.Float()


class ConceptsSchema(Schema):
    id = fields.Str()
    display_name = fields.Str()
    wikidata = fields.Str()
    relevance_score = fields.Float(attribute="meta.score")
    level = fields.Int()
    description = fields.Str()
    works_count = fields.Int()
    cited_by_count = fields.Int()
    ids = fields.Nested(IDsSchema)
    image_url = fields.Str()
    image_thumbnail_url = fields.Str()
    international = fields.Function(
        lambda obj: obj.international.to_dict()
        if "international" in obj and obj.international
        else None
    )
    ancestors = fields.List(fields.Nested(AncestorsSchema))
    related_concepts = fields.List(fields.Nested(RelatedConceptsSchema))
    counts_by_year = fields.List(fields.Nested(CountsByYearSchema))
    works_api_url = fields.Str()

    class Meta:
        ordered = True


class MessageSchema(Schema):
    meta = fields.Nested(MetaSchema)
    results = fields.Nested(ConceptsSchema, many=True)
    group_by = fields.Nested(GroupBySchema, many=True)

    class Meta:
        ordered = True
