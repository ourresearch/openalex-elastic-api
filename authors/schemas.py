from marshmallow import INCLUDE, Schema, fields, post_dump

from core.schemas import (CountsByYearSchema, GroupBySchema, MetaSchema,
                          XConceptsSchema)


class IDsSchema(Schema):
    openalex = fields.Str()
    orcid = fields.Str()
    mag = fields.Str()
    twitter = fields.Str()
    wikipedia = fields.Str()
    scopus = fields.Str()

    class Meta:
        ordered = True
        unknown = INCLUDE


class LastKnownInstitutionSchema(Schema):
    id = fields.Str()
    ror = fields.Str()
    display_name = fields.Str()
    country_code = fields.Str()
    type = fields.Str()

    class Meta:
        ordered = True
        unknown = INCLUDE


class AuthorsSchema(Schema):
    id = fields.Str()
    orcid = fields.Str()
    display_name = fields.Str()
    display_name_alternatives = fields.List(fields.Str())
    relevance_score = fields.Method("get_relevance_score")
    works_count = fields.Int()
    cited_by_count = fields.Int()
    ids = fields.Nested(IDsSchema)
    last_known_institution = fields.Nested(LastKnownInstitutionSchema)
    x_concepts = fields.List(fields.Nested(XConceptsSchema))
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

    class Meta:
        ordered = True


class MessageSchema(Schema):
    meta = fields.Nested(MetaSchema)
    results = fields.Nested(AuthorsSchema, many=True)
    group_by = fields.Nested(GroupBySchema, many=True)

    class Meta:
        ordered = True
