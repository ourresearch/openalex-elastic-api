from marshmallow import INCLUDE, Schema, fields, post_dump

from core.schemas import (
    GroupBySchema,
    GroupBysSchema,
    MetaSchema,
    hide_relevance,
    relevance_score,
)

# Import docstrings from fields
from awards.fields import DOCSTRINGS

class IdsSchema(Schema):
    id = fields.Str()
    type = fields.Str()
    asserted_by = fields.Str(default=None)

    class Meta:
        ordered = True
        unknown = INCLUDE

class AffiliationSchema(Schema):
    name = fields.Str()
    country = fields.Str(default=None)
    ids = fields.Nested(IdsSchema, many=True, default=None)

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
    name = fields.Str()
    ids = fields.Nested(IdsSchema, many=True, default=None)

    class Meta:
        ordered = True
        unknown = INCLUDE

class FundingSchema(Schema):
    type = fields.Str(default=None)
    scheme = fields.Str(default=None)
    funder = fields.Nested(FunderSchema, default=None)
    amount = fields.Float(default=None)
    currency = fields.Str(default=None)
    percentage = fields.Int(default=None)

    class Meta:
        ordered = True
        unknown = INCLUDE

class UrlsSchema(Schema):
    url = fields.Str()
    content_type = fields.Str(default=None)

class AwardsSchema(Schema):
    # Core identifiers
    id = fields.Int(metadata={"description": DOCSTRINGS["id"]})  # bigint in your data
    native_id = fields.Str(metadata={"description": DOCSTRINGS["native_id"]})
    award_id = fields.Str(default=None, metadata={"description": DOCSTRINGS["award_id"]})
    
    # Funded outputs
    funded_outputs = fields.List(fields.Str(), default=None, metadata={"description": DOCSTRINGS["funded_outputs"]})
    funded_outputs_count = fields.Int(default=None, metadata={"description": DOCSTRINGS["funded_outputs_count"]})
    
    # Award details
    title = fields.Str(metadata={"description": DOCSTRINGS["title"]})
    description = fields.Str(default=None, metadata={"description": DOCSTRINGS["description"]})
    
    # Funding information
    amount = fields.Float(default=None, metadata={"description": DOCSTRINGS["amount"]})
    currency = fields.Str(default=None, metadata={"description": DOCSTRINGS["currency"]})
    funding = fields.Nested(FundingSchema, default=None, metadata={"description": DOCSTRINGS["funding"]})
    
    # Dates
    start_date = fields.Str(default=None, metadata={"description": DOCSTRINGS["start_date"]})
    end_date = fields.Str(default=None, metadata={"description": DOCSTRINGS["end_date"]})
    planned_end_date = fields.Str(default=None, metadata={"description": DOCSTRINGS["planned_end_date"]})
    award_start_date = fields.Str(default=None, metadata={"description": DOCSTRINGS["award_start_date"]})
    accepted_date = fields.Str(default=None, metadata={"description": DOCSTRINGS["accepted_date"]})
    approved_date = fields.Str(default=None, metadata={"description": DOCSTRINGS["approved_date"]})
    issued_date = fields.Str(default=None, metadata={"description": DOCSTRINGS["issued_date"]})
    
    # URLs and identifiers
    landing_page = fields.Str(default=None, metadata={"description": DOCSTRINGS["landing_page"]})
    doi_url = fields.Str(default=None, metadata={"description": DOCSTRINGS["doi_url"]})
    doi = fields.Str(default=None, metadata={"description": "The Digital Object Identifier for the project"})
    
    # Publisher and metadata
    publisher = fields.Str(default=None, metadata={"description": DOCSTRINGS["publisher"]})
    member = fields.Str(default=None, metadata={"description": DOCSTRINGS["member"]})
    prefix = fields.Str(default=None, metadata={"description": DOCSTRINGS["prefix"]})
    provenance = fields.Str(default=None, metadata={"description": DOCSTRINGS["provenance"]})
    
    # Investigator information
    lead_investigator = fields.Nested(InvestigatorSchema, default=None, metadata={"description": DOCSTRINGS["lead_investigator"]})
    co_lead_investigator = fields.Nested(InvestigatorSchema, default=None, metadata={"description": DOCSTRINGS["co_lead_investigator"]})
    investigators = fields.Nested(InvestigatorSchema, many=True, default=None, metadata={"description": DOCSTRINGS["investigators"]})
    
    # Timestamps
    deposited_timestamp = fields.Str(default=None, metadata={"description": DOCSTRINGS["deposited_timestamp"]})
    created_timestamp = fields.Str(default=None, metadata={"description": DOCSTRINGS["created_timestamp"]})
    indexed_timestamp = fields.Str(default=None, metadata={"description": DOCSTRINGS["indexed_timestamp"]})
    indexed_date = fields.Str(default=None, metadata={"description": DOCSTRINGS["indexed_date"]})
    updated_date = fields.Str(default=None, metadata={"description": DOCSTRINGS["updated_date"]})
    
    # Computed fields
    aboutness = fields.Str(default=None, metadata={"description": DOCSTRINGS["aboutness"]})
    
    # URLs
    urls = fields.Nested(UrlsSchema, many=True, default=None)
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