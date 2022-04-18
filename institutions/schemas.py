from marshmallow import INCLUDE, Schema, fields, post_dump

from core.schemas import (CountsByYearSchema, GroupBySchema, MetaSchema,
                          XConceptsSchema)


class IDsSchema(Schema):
    openalex = fields.Str()
    ror = fields.Str()
    mag = fields.Str()
    grid = fields.Str()
    wikipedia = fields.Str()
    wikidata = fields.Str()

    class Meta:
        ordered = True
        unknown = INCLUDE


class GeoSchema(Schema):
    city = fields.Str()
    geonames_city_id = fields.Str()
    region = fields.Str()
    country_code = fields.Str()
    country = fields.Str()
    latitude = fields.Float()
    longitude = fields.Float()

    class Meta:
        ordered = True
        unknown = INCLUDE


class AssociatedInstitutionsSchema(Schema):
    id = fields.Str()
    ror = fields.Str()
    display_name = fields.Str()
    country_code = fields.Str()
    type = fields.Str()
    relationship = fields.Str()

    class Meta:
        ordered = True
        unknown = INCLUDE


class InstitutionsSchema(Schema):
    id = fields.Str()
    ror = fields.Str()
    display_name = fields.Str()
    relevance_score = fields.Method("get_relevance_score")
    country_code = fields.Str()
    type = fields.Str()
    homepage_url = fields.Str()
    image_url = fields.Str()
    image_thumbnail_url = fields.Str()
    display_name_acronyms = fields.List(fields.Str())
    display_name_alternatives = fields.List(fields.Str())
    works_count = fields.Int()
    cited_by_count = fields.Int()
    ids = fields.Nested(IDsSchema)
    geo = fields.Nested(GeoSchema)
    international = fields.Function(
        lambda obj: obj.international.to_dict()
        if "international" in obj and obj.international
        else None
    )
    associated_institutions = fields.List(fields.Nested(AssociatedInstitutionsSchema))
    counts_by_year = fields.List(fields.Nested(CountsByYearSchema))
    x_concepts = fields.List(fields.Nested(XConceptsSchema))
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

    class Meta:
        ordered = True


class MessageSchema(Schema):
    meta = fields.Nested(MetaSchema)
    results = fields.Nested(InstitutionsSchema, many=True)
    group_by = fields.Nested(GroupBySchema, many=True)

    class Meta:
        ordered = True
