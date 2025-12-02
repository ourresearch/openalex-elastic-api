from marshmallow import INCLUDE, Schema, fields, post_dump

from core.schemas import (
    GroupBySchema,
    GroupBysSchema,
    MetaSchema,
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


class AwardsSchema(Schema):
    id = fields.Str()
    display_name = fields.Str(default=None)
    description = fields.Str(default=None)
    funder_award_id = fields.Str(default=None)
    
    # Funded outputs
    funded_outputs = fields.List(fields.Str(), default=None)
    funded_outputs_count = fields.Int(default=None)
    
    # Funding information (flat structure as per actual document)
    amount = fields.Float(default=None)
    currency = fields.Str(default=None)
    funder = fields.Nested(FunderSchema)
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