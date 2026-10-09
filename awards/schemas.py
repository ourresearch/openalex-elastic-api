from marshmallow import INCLUDE, Schema, fields, post_dump

from core.schemas import (
    GroupBySchema,
    GroupBysSchema,
    MetaSchema,
    TopicSchema,
    hide_relevance,
    relevance_score,
)

class AffiliationIdSchema(Schema):
    id = fields.Str()
    type = fields.Str()
    asserted_by = fields.Str()

    class Meta:
        ordered = True
        unknown = INCLUDE


class AffiliationSchema(Schema):
    name = fields.Str()
    country = fields.Str(default=None)
    ids = fields.List(fields.Nested(AffiliationIdSchema), default=None)

    class Meta:
        ordered = True
        unknown = INCLUDE


class InvestigatorSchema(Schema):
    given_name = fields.Str(default=None)
    family_name = fields.Str(default=None)
    orcid = fields.Str(default=None)
    role_start = fields.Str(default=None)
    affiliation = fields.Nested(AffiliationSchema, default=None)

    class Meta:
        ordered = True
        unknown = INCLUDE


class FunderSchema(Schema):
    id = fields.Str()
    display_name = fields.Str()
    ror = fields.Str()
    doi = fields.Str()

    class Meta:
        ordered = True
        unknown = INCLUDE


class InstitutionAwardedSchema(Schema):
    id = fields.Str()
    display_name = fields.Str()
    ror = fields.Str(default=None)
    country_code = fields.Str(default=None)
    type = fields.Str(default=None)
    lineage = fields.List(fields.Str(), default=None)

    class Meta:
        ordered = True
        unknown = INCLUDE


class RelatedAwardFunderSchema(Schema):
    id = fields.Str(allow_none=True)
    display_name = fields.Str(allow_none=True)


class RelatedAwardSchema(Schema):
    id = fields.Str()
    display_name = fields.Str(allow_none=True)
    funder = fields.Nested(RelatedAwardFunderSchema)
    relationship = fields.Str()
    asserted_by = fields.Str()


class RecipientCountrySchema(Schema):
    country_code = fields.Str()
    share = fields.Float(allow_none=True)
    amount_usd = fields.Float(allow_none=True)
    basis = fields.Str(allow_none=True)

    class Meta:
        ordered = True


class RecipientRegionSchema(Schema):
    code = fields.Str()
    vocabulary = fields.Str(allow_none=True)
    display_name = fields.Str(allow_none=True)
    share = fields.Float(allow_none=True)

    class Meta:
        ordered = True


class ResearchScopeSchema(Schema):
    is_research = fields.Bool(allow_none=True)
    basis = fields.Str(allow_none=True)
    tier = fields.Int(allow_none=True)

    class Meta:
        ordered = True


class AwardsSchema(Schema):
    id = fields.Str()
    display_name = fields.Str(default=None)
    description = fields.Str(default=None)
    funder_award_id = fields.Str(default=None)
    funder = fields.Nested(FunderSchema)
    
    # Funded outputs
    funded_outputs = fields.List(fields.Str(), default=None)
    funded_outputs_count = fields.Int(default=None)
    
    parent_awards = fields.List(fields.Nested(RelatedAwardSchema), dump_default=list)
    sub_awards = fields.List(fields.Nested(RelatedAwardSchema), dump_default=list)
    sub_awards_count = fields.Int(dump_default=0)

    # Funding information (flat structure as per actual document)
    amount = fields.Float(default=None)
    currency = fields.Str(default=None)
    # Funding-flows release (oxjob #1570): USD amount at the start-date rate, where the money lands, research flag.
    amount_usd = fields.Float(default=None)
    amount_usd_basis = fields.Str(default=None)
    recipient_countries = fields.List(fields.Nested(RecipientCountrySchema), dump_default=list)
    recipient_regions = fields.List(fields.Nested(RecipientRegionSchema), dump_default=list)
    research_scope = fields.Nested(ResearchScopeSchema, default=None)
    funding_type = fields.Str(default=None)
    funder_scheme = fields.Str(default=None)
    
    # Dates
    start_date = fields.Str(default=None)
    end_date = fields.Str(default=None)
    start_year = fields.Int(default=None)
    end_year = fields.Int(default=None)
    
    # URLs and identifiers
    landing_page_url = fields.Str(default=None)
    doi = fields.Str(default=None)

    provenance = fields.Str(default=None)
    
    # Investigator information
    lead_investigator = fields.Nested(InvestigatorSchema, default=None)
    co_lead_investigator = fields.Nested(InvestigatorSchema, default=None)
    investigators = fields.List(fields.Nested(InvestigatorSchema), default=None)

    works_api_url = fields.Str(default=None)

    # Topic classification (oxjob #123.1)
    primary_topic = fields.Nested(TopicSchema, default=None)
    topics = fields.Nested(TopicSchema, many=True, default=None)

    # Institution(s) that received the award (oxjob #123.2)
    institution_awarded = fields.Nested(InstitutionAwardedSchema, many=True, default=None)

    updated_date = fields.Str(default=None)
    created_date = fields.Str(default=None)

    # Computed fields
    relevance_score = fields.Method("get_relevance_score")

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
    results = fields.Nested(AwardsSchema, many=True)
    group_by = fields.Nested(GroupBySchema, many=True)
    group_bys = fields.Nested(GroupBysSchema, many=True)

    class Meta:
        ordered = True