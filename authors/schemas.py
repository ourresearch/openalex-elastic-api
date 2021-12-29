from marshmallow import INCLUDE, Schema, fields

from core.schemas import GroupBySchema, MetaSchema


class IDsSchema(Schema):
    openalex = fields.Str()
    orcid = fields.Str()
    scopus = fields.Str()
    twitter = fields.Str()
    wikipedia = fields.Str()
    mag = fields.Str()

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


class CountsByYearSchema(Schema):
    year = fields.Int()
    works_count = fields.Int()
    cited_by_count = fields.Int()

    class Meta:
        ordered = True
        unknown = INCLUDE


class XConceptsSchema(Schema):
    id = fields.Str()
    wikidata = fields.Str()
    display_name = fields.Str()
    level = fields.Int()
    score = fields.Float()


class AuthorsSchema(Schema):
    id = fields.Str()
    display_name = fields.Str()
    display_name_alternatives = fields.List(fields.Str())
    relevance_score = fields.Float(attribute="meta.score")
    orcid = fields.Str()
    works_count = fields.Int()
    cited_by_count = fields.Int()
    ids = fields.Nested(IDsSchema)
    last_known_institution = fields.Nested(LastKnownInstitutionSchema)
    counts_by_year = fields.List(fields.Nested(CountsByYearSchema))
    x_concepts = fields.List(fields.Nested(XConceptsSchema))
    works_api_url = fields.Str()

    class Meta:
        ordered = True


class MessageSchema(Schema):
    meta = fields.Nested(MetaSchema)
    results = fields.Nested(AuthorsSchema, many=True)
    group_by = fields.Nested(GroupBySchema, many=True)

    class Meta:
        ordered = True
