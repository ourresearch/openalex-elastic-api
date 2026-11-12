from core.fields import (
    BooleanField,
    CollectionField,
    DateField,
    DateTimeField,
    OpenAlexIDField,
    OpenAlexURLTermField,
    RangeField,
    SearchField,
    TermField,
    TextTermField,
    JoinField,
    annotate_entity_types,
)

fields = [
    # Sync filters (oxjob #1917): the docs promise from_created_date / from_updated_date on every entity type;
    # awards had none (HTTP 400) though 119,624 awards changed on 29 Oct 2026.
    DateField(
        param="from_created_date",
        custom_es_field="created_date",
    ),
    DateField(
        param="to_created_date",
        custom_es_field="created_date",
    ),
    DateTimeField(
        param="from_updated_date",
        custom_es_field="updated_date",
    ),
    DateTimeField(
        param="to_updated_date",
        custom_es_field="updated_date",
    ),
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
        custom_es_field="doi.keyword",  # `doi` is text: a whole DOI never matched (oxjob #1901)
        docstring="The Digital Object Identifier for the project",
        sort_field="doi.keyword",
    ),
    OpenAlexURLTermField(  # id:G2966666733 = its URL form (oxjob #2140, ticket 22928)
        param="id",
        custom_es_field="id"
    ),
    TermField(
        param="funder_award_id"
    ),
    TermField(
        param="provenance"
    ),
    TextTermField(  # text, no keyword copy: a term query never matched (oxjob #1901)
        param="lead_investigator.given_name",
        custom_es_field="lead_investigator.given_name",
        docstring="The given name of the lead investigator",
        sortable=False,
    ),
    TextTermField(  # text, no keyword copy: a term query never matched (oxjob #1901)
        param="lead_investigator.family_name",
        custom_es_field="lead_investigator.family_name",
        docstring="The family name of the lead investigator",
        sortable=False,
    ),
    TermField(
        param="lead_investigator.orcid", 
        custom_es_field="lead_investigator.orcid",
        docstring="The ORCID identifier of the lead investigator"
    ),
    TextTermField(  # text, no keyword copy: a term query never matched (oxjob #1901)
        param="lead_investigator.affiliation.name",
        custom_es_field="lead_investigator.affiliation.name",
        docstring="The institutional affiliation of the lead investigator",
        sortable=False,
    ),
    TermField(
        param="lead_investigator.affiliation.country",
        custom_es_field="lead_investigator.affiliation.country",
        docstring="The country of the lead investigator's affiliation"
    ),
    # Grants on author profiles (oxjob #1847). investigators.author.id covers everyone named on the award (lead, co-lead
    # and investigators[]) through the investigators_full object sibling (the authorships_full pattern; awards-v4 maps
    # both author ids as keyword). A merged-away author id also matches its winner (OpenAlexIDField).
    OpenAlexIDField(
        param="lead_investigator.author.id",
        custom_es_field="lead_investigator.author.id",
        entity_type="authors",
        docstring="The OpenAlex ID of the lead investigator's author profile",
    ),
    OpenAlexIDField(
        param="investigators.author.id",
        custom_es_field="investigators_full.author.id",
        entity_type="authors",
        docstring="The OpenAlex ID of the author profile of anyone named on the award: lead, co-lead or other investigator",
    ),
    # Each person's institutions (oxjob #1847, item 9: Nightly Grants fills lead_investigator / investigators[].institutions[]
    # as works' authorships.institutions). Works' authorships.institutions.id on the keyword lead_investigator.institutions.id /
    # investigators_full.institutions.id (PatchInvestigatorAuthorsMapping maps both); full or short id. Institution ids are not
    # merge-resolved (core.merged_ids covers work, author, source and funder ids only), as on works.
    OpenAlexIDField(
        param="lead_investigator.institutions.id",
        custom_es_field="lead_investigator.institutions.id",
        entity_type="institutions",
        docstring="The OpenAlex ID of an institution the lead investigator's affiliation matched",
    ),
    OpenAlexIDField(
        param="investigators.institutions.id",
        custom_es_field="investigators_full.institutions.id",
        entity_type="institutions",
        docstring="The OpenAlex ID of an institution the affiliation of anyone named on the award matched: lead, co-lead or other investigator",
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
    # Keywords and SDGs (oxjob #2125). awards-v4 maps both as the works index does (object, keyword id), so these are works'
    # filters: the same params, the same accepted values (a keyword's slug or id; an SDG's number, sdgs/N or either URL).
    TermField(
        param="keywords.id",
        custom_es_field="keywords.id",
        docstring="The OpenAlex ID of a keyword the award's title and description were tagged with",
    ),
    TermField(
        param="sustainable_development_goals.id",
        docstring="The award's relevance to one or more of the United Nations' Sustainable Development Goals",
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
        sortable=False,
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
    OpenAlexIDField(param="parent_awards.id", custom_es_field="parent_awards_full.id", entity_type="awards",
                    docstring="The OpenAlex ID of an award this award is part of, or was re-granted from"),
    OpenAlexIDField(param="sub_awards.id", custom_es_field="sub_awards_full.id", entity_type="awards",
                    docstring="The OpenAlex ID of an award that is part of, or re-granted from, this award"),
    OpenAlexIDField(param="parent_awards.funder.id", custom_es_field="parent_awards_full.funder.id", entity_type="funders",
                    docstring="The OpenAlex ID of the funder of a parent award (e.g. every award that Wellcome money flowed into through another organisation)"),
    OpenAlexIDField(param="sub_awards.funder.id", custom_es_field="sub_awards_full.funder.id", entity_type="funders",
                    docstring="The OpenAlex ID of the funder of a sub-award"),
    TermField(param="parent_awards.relationship", custom_es_field="parent_awards_full.relationship",
              docstring="How this award relates to a parent award: sub_award (re-granted to another organisation) or component (part of a larger award from the same funder)"),
    TermField(param="sub_awards.relationship", custom_es_field="sub_awards_full.relationship",
              docstring="How a sub-award relates to this award: sub_award or component"),
    BooleanField(param="has_parent_award", custom_es_field="parent_awards_full.id",
                 docstring="Whether the award is part of, or re-granted from, another award (true when it lists any parent_awards)"),
    RangeField(param="sub_awards_count", custom_es_field="sub_awards_count",
               docstring="The number of awards that are part of, or re-granted from, this award"),
    # Funding-flows release (walden Nightly Grants, oxjob #1570): USD amount, where the money lands, research flag.
    RangeField(param="amount_usd", custom_es_field="amount_usd",
               docstring="The award amount in US dollars, converted at the exchange rate of the start date (amount and currency are unchanged)"),
    TermField(param="amount_usd_basis", custom_es_field="amount_usd_basis",
              docstring="How amount_usd was derived: usd_native, daily_rate or annual_average"),
    TermField(param="recipient_countries.country_code", custom_es_field="recipient_countries_full.country_code.lower",
              docstring="A country where the award's money lands (ISO 3166-1 alpha-2), as the funder reports it or the place of performance"),
    TermField(param="recipient_countries.continent", alias="recipient_countries_full.country_code",
              docstring="A continent where the award's money lands", sortable=False),
    TermField(param="recipient_countries.basis", custom_es_field="recipient_countries_full.basis",
              docstring="How a recipient country is known: funder_reported, place_of_performance or organisation_location"),
    OpenAlexIDField(param="recipients.id", custom_es_field="recipients_full.id",
                    docstring="The OpenAlex ID of an organisation that received money from the award"),
    TermField(param="recipients.ror", custom_es_field="recipients_full.ror",
              docstring="The ROR ID of an organisation that received money from the award"),
    TermField(param="recipient_regions.code", custom_es_field="recipient_regions_full.code",
              docstring="A region where the award's money lands when the funder names no country (OECD DAC region code)"),
    BooleanField(param="has_recipient_country", custom_es_field="recipient_countries_full.country_code",
                 docstring="Whether the award names at least one country where its money lands"),
    BooleanField(param="research_scope.is_research", custom_es_field="research_scope.is_research",
                 docstring="Whether the award is research funding: to a research organisation, or about research (absent when unknown)"),
    TermField(param="research_scope.basis", custom_es_field="research_scope.basis",
              docstring="How the research flag was decided: funder_default, programme_rule, sector_code, recipient_type or unknown"),
    CollectionField(entity_type="awards"),
    # oxjob #1526: the funder's country, looked up in the funders index (filter only).
    JoinField(param="funder.country_code", target_entity="funders", target_param="country_code",
              local_field="funder.id", like=TermField, entity_type="countries",
              docstring="The country of the award's funder"),
]

# Awards never ran this, so its institution, topic and country columns carried no
# entity_type: the Advanced search value picker had nothing to search ("No matches").
annotate_entity_types(fields)

fields_dict = {f.param: f for f in fields}