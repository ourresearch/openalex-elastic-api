from marshmallow import INCLUDE, Schema, fields, post_dump

from core.schemas import (CountsByYearSchema, GroupBySchema, GroupBysSchema,
                          MetaSchema, SummaryStatsSchema, XConceptsSchema,
                          hide_relevance, relevance_score)


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


class InstitutionSchema(Schema):
    id = fields.Str()
    ror = fields.Str()
    display_name = fields.Str()
    country_code = fields.Str()
    type = fields.Str()
    lineage = fields.List(fields.Str())

    class Meta:
        ordered = True
        unknown = INCLUDE


class AffiliationSchema(Schema):
    institution = fields.Nested(InstitutionSchema)
    years = fields.List(fields.Int())

    class Meta:
        ordered = True


class AuthorsSchema(Schema):
    id = fields.Str()
    orcid = fields.Str()
    display_name = fields.Str()
    display_name_alternatives = fields.List(fields.Str())
    relevance_score = fields.Method("get_relevance_score")
    works_count = fields.Int()
    cited_by_count = fields.Int()
    summary_stats = fields.Nested(SummaryStatsSchema, dump_default=None)
    ids = fields.Nested(IDsSchema)
    affiliations = fields.List(fields.Nested(AffiliationSchema))
    last_known_institution = fields.Nested(InstitutionSchema)
    x_concepts = fields.List(fields.Nested(XConceptsSchema))
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

    class Meta:
        ordered = True


class MessageSchema(Schema):
    meta = fields.Nested(MetaSchema)
    results = fields.Nested(AuthorsSchema, many=True)
    group_by = fields.Nested(GroupBySchema, many=True)
    group_bys = fields.Nested(GroupBysSchema, many=True)

    class Meta:
        ordered = True
