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

# Custom field to handle AttrList serialization
class AttrListField(fields.Field):
    def _serialize(self, value, attr, obj, **kwargs):
        if value is None:
            return None
        # Convert AttrList to regular list
        if hasattr(value, '__iter__') and not isinstance(value, (str, bytes)):
            return list(value)
        return value

class AffiliationSchema(Schema):
    name = fields.Str()
    country = fields.Str(default=None)
    ids = fields.Raw(default=None)

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

class FunderIdsSchema(Schema):
    ror_id = fields.Str(default=None)
    doi = fields.Str(default=None)

    class Meta:
        ordered = True
        unknown = INCLUDE

class AwardsSchema(Schema):
    # Core identifiers
    id = fields.Str(metadata={"description": DOCSTRINGS["id"]})
    award_id = fields.Str(default=None, metadata={"description": DOCSTRINGS["award_id"]})
    
    # Funded outputs
    funded_outputs = AttrListField(default=None, metadata={"description": DOCSTRINGS["funded_outputs"]})
    funded_outputs_count = fields.Int(default=None, metadata={"description": DOCSTRINGS["funded_outputs_count"]})
    
    # Award details
    title = fields.Str(metadata={"description": DOCSTRINGS["title"]})
    description = fields.Str(default=None, metadata={"description": DOCSTRINGS["description"]})
    
    # Funding information (flat structure as per actual document)
    amount = fields.Float(default=None, metadata={"description": DOCSTRINGS["amount"]})
    currency = fields.Str(default=None, metadata={"description": DOCSTRINGS["currency"]})
    funder_id = fields.Str(default=None, metadata={"description": "The funder's OpenAlex ID"})
    funder_name = fields.Str(default=None, metadata={"description": "The name of the funding organization"})
    funding_type = fields.Str(default=None, metadata={"description": "The type of funding provided"})
    funder_scheme = fields.Str(default=None, metadata={"description": "The specific funding scheme or program"})
    funder_ids = fields.Nested(FunderIdsSchema, default=None, metadata={"description": "The funder's external identifiers"})
    
    # Dates
    start_date = fields.Str(default=None, metadata={"description": DOCSTRINGS["start_date"]})
    end_date = fields.Str(default=None, metadata={"description": DOCSTRINGS["end_date"]})
    planned_end_date = fields.Str(default=None, metadata={"description": DOCSTRINGS["planned_end_date"]})
    accepted_date = fields.Str(default=None, metadata={"description": DOCSTRINGS["accepted_date"]})
    approved_date = fields.Str(default=None, metadata={"description": DOCSTRINGS["approved_date"]})
    issued_date = fields.Str(default=None, metadata={"description": DOCSTRINGS["issued_date"]})
    
    # URLs and identifiers
    landing_page = fields.Str(default=None, metadata={"description": DOCSTRINGS["landing_page"]})
    doi_url = fields.Str(default=None, metadata={"description": DOCSTRINGS["doi_url"]})
    doi = fields.Str(default=None, metadata={"description": "The Digital Object Identifier for the project"})
    
    # Publisher and metadata
    publisher = fields.Str(default=None, metadata={"description": DOCSTRINGS["publisher"]})
    member_id = fields.Str(default=None, metadata={"description": "The member ID associated with the project"})
    provenance = fields.Str(default=None, metadata={"description": DOCSTRINGS["provenance"]})
    
    # Investigator information
    lead_investigator = fields.Nested(InvestigatorSchema, default=None, metadata={"description": DOCSTRINGS["lead_investigator"]})
    co_lead_investigator = fields.Nested(InvestigatorSchema, default=None, metadata={"description": DOCSTRINGS["co_lead_investigator"]})
    investigators = AttrListField(default=None, metadata={"description": DOCSTRINGS["investigators"]})
    
    # Timestamps
    deposited_timestamp = fields.Str(default=None, metadata={"description": DOCSTRINGS["deposited_timestamp"]})
    created_timestamp = fields.Str(default=None, metadata={"description": DOCSTRINGS["created_timestamp"]})
    indexed_timestamp = fields.Str(default=None, metadata={"description": DOCSTRINGS["indexed_timestamp"]})
    
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