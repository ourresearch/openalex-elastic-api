from core.fields import (
    OpenAlexIDField,
    RangeField,
    SearchField,
    TermField,
)

fields = [
    OpenAlexIDField(
        param="funder.id",
        entity_type="funders",
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
    SearchField(param="text.search", index="awards"),
    SearchField(param="default.search", index="awards", alternate_of="text.search"),
    SearchField(param="description.search", custom_es_field="description", index="awards"),
    SearchField(param="display_name.search", custom_es_field="display_name", index="awards"),
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
        # ES maps `funder_scheme` as `text` (unlike sibling keyword fields), so a
        # terms agg / term filter on the bare field 500s ("fielddata disabled").
        # Point at the `.keyword` subfield — same pattern as display_name.keyword
        # everywhere. Fixes both group_by (#316) and exact-match filtering.
        custom_es_field="funder_scheme.keyword",
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
    # Topic classification (oxjob #123.1, finalized in #123.2). awards-v4 has
    # `primary_topic` and `topics` declared as `nested`, with denormalized
    # `primary_topic_full` and `topics_full` siblings (object mapping, `keyword`
    # id fields) for fast term filtering. This mirrors the works pattern of
    # `authorships` (nested) + `authorships_full` (denormalized). Filters route
    # to the `_full` variants; the `.keyword` suffix workaround is no longer
    # needed.
    OpenAlexIDField(
        param="primary_topic.id",
        custom_es_field="primary_topic_full.id",
    ),
    OpenAlexIDField(
        param="topics.id",
        custom_es_field="topics_full.id",
    ),
    TermField(
        param="primary_topic.domain.id",
        custom_es_field="primary_topic_full.domain.id",
    ),
    TermField(
        param="primary_topic.field.id",
        custom_es_field="primary_topic_full.field.id",
    ),
    TermField(
        param="primary_topic.subfield.id",
        custom_es_field="primary_topic_full.subfield.id",
    ),
    TermField(
        param="topics.domain.id",
        custom_es_field="topics_full.domain.id",
    ),
    TermField(
        param="topics.field.id",
        custom_es_field="topics_full.field.id",
    ),
    TermField(
        param="topics.subfield.id",
        custom_es_field="topics_full.subfield.id",
    ),
    # institution_awarded (oxjob #123.2). awards-v4 has `institution_awarded`
    # as nested with a denormalized `institution_awarded_full` (object mapping)
    # sibling for filtering. Filter set mirrors the works `institutions.*`
    # subset.
    OpenAlexIDField(
        param="institution_awarded.id",
        custom_es_field="institution_awarded_full.id",
        docstring="The OpenAlex ID of the institution that received the award",
    ),
    TermField(
        param="institution_awarded.ror",
        custom_es_field="institution_awarded_full.ror",
        docstring="The ROR ID of the institution that received the award",
    ),
    TermField(
        param="institution_awarded.country_code",
        # Route to the `.lower` normalized subfield so the filter is
        # case-insensitive, matching every other entity's country_code field
        # (works/authors/institutions/sources route there via alias -> __lower;
        # publishers via custom_es_field="country_codes.lower"). The bare
        # `keyword` is case-sensitive and the gui sends lowercased ids, so
        # `country_code:us` silently returned 0. The `.lower` subfield + the
        # `lower` normalizer were added to awards-v4 in oxjob #256 (mirrored in
        # the walden BuildAwardsV4 / PatchAwardsV4Mapping notebooks).
        custom_es_field="institution_awarded_full.country_code.lower",
        docstring="The country of the institution that received the award",
    ),
    TermField(
        param="institution_awarded.continent",
        alias="institution_awarded_full.country_code",
        docstring="The continent of the institution that received the award",
    ),
    TermField(
        param="institution_awarded.type",
        custom_es_field="institution_awarded_full.type",
        docstring="The type of the institution that received the award (e.g. education, healthcare)",
    ),
    OpenAlexIDField(
        param="institution_awarded.lineage",
        custom_es_field="institution_awarded_full.lineage",
        docstring="The OpenAlex ID of an ancestor of the institution that received the award",
    ),
]

fields_dict = {f.param: f for f in fields}