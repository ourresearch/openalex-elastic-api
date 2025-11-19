from core.fields import (
    BooleanField,
    DateField,
    DateTimeField,
    OpenAlexIDField,
    RangeField,
    SearchField,
    TermField,
)

# shared docstrings for when multiple fields share the same docstring (such as aliases)
DOCSTRINGS = {
    "id": "A unique numeric identifier for the project, which can be used for database operations and queries",
    "native_id": "An identifier used in the original system or database where the project was recorded, facilitating cross-referencing",
    "award_id": "The identifier for the specific funding award associated with the project, useful for linking to funding sources",
    "funder_award_id": "The identifier for the specific funding award associated with the project, useful for linking to funding sources",
    "amount": "The total amount of funding allocated to the project, which is essential for financial analysis",
    "currency": "The currency in which the funding amount is denominated, providing context for financial figures",
    "title": "The title of the research project, giving a brief overview of its focus and objectives",
    "description": "A detailed description of the project, outlining its goals, methodologies, and significance",
    "start_date": "The date when the project officially begins, important for tracking project timelines",
    "end_date": "The date when the project is expected to conclude, useful for assessing project duration",
    "planned_end_date": "The anticipated end date for the project, which may differ from the actual end date and is useful for project management",
    "award_start_date": "The date when the funding award officially begins, important for financial tracking",
    "accepted_date": "The date when the project proposal was accepted for funding, marking a key milestone in the project timeline",
    "approved_date": "The date when the project received formal approval, which is critical for compliance and governance",
    "issued_date": "The date when the funding was officially issued to the project, relevant for financial reporting",
    "landing_page": "The main web link associated with the project, which can direct users to more information or resources",
    "doi_url": "The Digital Object Identifier link for the project, facilitating easy access to published research outputs",
    "publisher": "The name of the publisher associated with the project, relevant for understanding dissemination channels",
    "member": "Information about any organizational or institutional membership related to the project, which may influence funding or collaboration",
    "prefix": "A prefix that may be used for categorizing or identifying the project within a specific framework or system",
    "provenance": "Information about the origin and history of the project data, important for data integrity and validation",
    "deposited_timestamp": "The timestamp indicating when the project data was deposited into the system, useful for tracking data updates",
    "created_timestamp": "The timestamp marking when the project record was created, important for historical reference",
    "indexed_timestamp": "The timestamp indicating when the project was indexed for search and retrieval, relevant for data accessibility",
    "indexed_date": "The date when the project was indexed, providing context for data availability",
    "updated_date": "The date when the project record was last updated, important for maintaining current information",
    "funded_outputs": "The works funded by this award, providing insight into research outputs and impact",
    "funded_outputs_count": "The number of works funded by this award, useful for assessing research productivity",
    "aboutness": "A summary of the project's focus and research areas, generated from title and description",
    "lead_investigator": "Information about the primary researcher leading the project, crucial for understanding leadership roles",
    "co_lead_investigator": "Details about any co-lead researchers involved in the project, highlighting collaborative efforts",
    "investigators": "A list of all researchers involved in the project, providing insight into team composition and expertise",
    "funding": "Details about the funding structure, including types and sources of funding, which can help in understanding financial support",
}

fields = [
    # Core identifiers
    TermField(
        param="id", 
        custom_es_field="id",
        docstring=DOCSTRINGS["id"]
    ),
    TermField(
        param="funder_award_id",
        custom_es_field="funder_award_id",
        docstring=DOCSTRINGS["funder_award_id"]
    ),
    
    # Funded outputs
    OpenAlexIDField(
        param="funded_outputs",
        alias="funded_outputs",
        docstring=DOCSTRINGS["funded_outputs"],
    ),
    RangeField(
        param="funded_outputs_count", 
        custom_es_field="funded_outputs_count",
        docstring=DOCSTRINGS["funded_outputs_count"]
    ),
    
    # Award details
    SearchField(param="default.search", index="awards"),
    SearchField(
        param="title.search",
        unique_id="award_search",
    ),
    TermField(
        param="description", 
        custom_es_field="description",
        docstring=DOCSTRINGS["description"]
    ),
    
    # Funding information
    RangeField(
        param="amount", 
        custom_es_field="amount",
        docstring=DOCSTRINGS["amount"]
    ),
    TermField(
        param="currency", 
        custom_es_field="currency",
        docstring=DOCSTRINGS["currency"]
    ),
    OpenAlexIDField(
        param="funder.id",
        docstring="The funder's OpenAlex ID",
    ),
    TermField(
        param="funder_name", 
        custom_es_field="funder_name",
        docstring="The name of the funding organization"
    ),
    TermField(
        param="funding_type", 
        custom_es_field="funding_type",
        docstring="The type of funding provided"
    ),
    TermField(
        param="funder_scheme", 
        custom_es_field="funder_scheme",
        docstring="The specific funding scheme or program"
    ),
    TermField(
        param="funder.ror",
        custom_es_field="funder.ror",
        docstring="The ROR ID of the funding organization"
    ),
    TermField(
        param="funder.doi",
        custom_es_field="funder.doi",
        docstring="The DOI of the funding organization"
    ),
    # Dates
    DateField(
        param="start_date", 
        custom_es_field="start_date",
        docstring=DOCSTRINGS["start_date"]
    ),
    DateField(
        param="end_date", 
        custom_es_field="end_date",
        docstring=DOCSTRINGS["end_date"]
    ),
    DateField(
        param="planned_end_date", 
        custom_es_field="planned_end_date",
        docstring=DOCSTRINGS["planned_end_date"]
    ),
    DateField(
        param="accepted_date", 
        custom_es_field="accepted_date",
        docstring=DOCSTRINGS["accepted_date"]
    ),
    DateField(
        param="approved_date", 
        custom_es_field="approved_date",
        docstring=DOCSTRINGS["approved_date"]
    ),
    DateField(
        param="issued_date", 
        custom_es_field="issued_date",
        docstring=DOCSTRINGS["issued_date"]
    ),
    
    # URLs and identifiers
    TermField(
        param="landing_page", 
        custom_es_field="landing_page",
        docstring=DOCSTRINGS["landing_page"]
    ),
    TermField(
        param="doi_url", 
        custom_es_field="doi_url",
        docstring=DOCSTRINGS["doi_url"]
    ),
    TermField(
        param="doi", 
        custom_es_field="doi",
        docstring="The Digital Object Identifier for the project"
    ),
    
    # Publisher and metadata
    TermField(
        param="publisher", 
        custom_es_field="publisher",
        docstring=DOCSTRINGS["publisher"]
    ),
    TermField(
        param="member_id", 
        custom_es_field="member_id",
        docstring="The member ID associated with the project"
    ),
    TermField(
        param="provenance", 
        custom_es_field="provenance",
        docstring=DOCSTRINGS["provenance"]
    ),
    
    # Investigator information
    TermField(
        param="lead_investigator.given_name", 
        custom_es_field="lead_investigator.given_name",
        docstring="The given name of the lead investigator"
    ),
    TermField(
        param="lead_investigator.family_name", 
        custom_es_field="lead_investigator.family_name",
        docstring="The family name of the lead investigator"
    ),
    TermField(
        param="lead_investigator.orcid", 
        custom_es_field="lead_investigator.orcid",
        docstring="The ORCID identifier of the lead investigator"
    ),
    TermField(
        param="lead_investigator.affiliation.name", 
        custom_es_field="lead_investigator.affiliation.name",
        docstring="The institutional affiliation of the lead investigator"
    ),
    TermField(
        param="lead_investigator.affiliation.country", 
        custom_es_field="lead_investigator.affiliation.country",
        docstring="The country of the lead investigator's affiliation"
    ),
    
    # Co-lead investigator
    TermField(
        param="co_lead_investigator.given_name", 
        custom_es_field="co_lead_investigator.given_name",
        docstring="The given name of the co-lead investigator"
    ),
    TermField(
        param="co_lead_investigator.family_name", 
        custom_es_field="co_lead_investigator.family_name",
        docstring="The family name of the co-lead investigator"
    ),
    TermField(
        param="co_lead_investigator.orcid", 
        custom_es_field="co_lead_investigator.orcid",
        docstring="The ORCID identifier of the co-lead investigator"
    ),
    TermField(
        param="co_lead_investigator.affiliation.name", 
        custom_es_field="co_lead_investigator.affiliation.name",
        docstring="The institutional affiliation of the co-lead investigator"
    ),
    TermField(
        param="co_lead_investigator.affiliation.country", 
        custom_es_field="co_lead_investigator.affiliation.country",
        docstring="The country of the co-lead investigator's affiliation"
    ),
    
    # Additional investigators
    TermField(
        param="investigators", 
        custom_es_field="investigators",
        docstring="A list of all researchers involved in the project"
    ),
    
    # Timestamps
    DateTimeField(
        param="created_timestamp",
        custom_es_field="created_timestamp",
        docstring=DOCSTRINGS["created_timestamp"]
    )
]

fields_dict = {f.param: f for f in fields}