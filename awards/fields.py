from core.fields import (
    OpenAlexIDField,
    RangeField,
    TermField,
)

fields = [
    OpenAlexIDField(
        param="funder.id",
        docstring="The funder's OpenAlex ID",
    ),
    OpenAlexIDField(
        param="funded_outputs",
        alias="funded_outputs",
    ),
    RangeField(
        param="funded_outputs_count", 
        custom_es_field="funded_outputs_count"
    ),
    RangeField(
        param="amount", 
        custom_es_field="amount"
    ),
    RangeField(
        param="end_year",
        docstring="The year when the project is expected to conclude"
    ),
    RangeField(
        param="start_year",
        docstring="The year when the project officially begins"
    ),
    TermField(
        param="currency",
        custom_es_field="currency"
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
    TermField(
        param="doi", 
        custom_es_field="doi",
        docstring="The Digital Object Identifier for the project"
    ),
    TermField(
        param="id",
        custom_es_field="id"
    ),
    TermField(
        param="funder_award_id"
    ),
    TermField(
        param="provenance"
    ),
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
]

fields_dict = {f.param: f for f in fields}