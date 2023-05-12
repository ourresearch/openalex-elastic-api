from core.fields import (BooleanField, DateField, DateTimeField,
                         OpenAlexIDField, PhraseField, RangeField, SearchField,
                         TermField)

fields = [
    BooleanField(
        param=f"authorships.institutions.is_global_south",
        custom_es_field="authorships.institutions.country_code",
    ),
    BooleanField(param="best_oa_location.is_oa"),
    BooleanField(param="authorships.is_corresponding"),
    BooleanField(
        param=f"institutions.is_global_south",
        custom_es_field="authorships.institutions.country_code",
    ),
    BooleanField(param="has_abstract", custom_es_field="abstract"),
    BooleanField(param="has_doi", custom_es_field="ids.doi"),
    BooleanField(param="has_fulltext", custom_es_field="fulltext"),
    BooleanField(
        param="has_orcid",
        custom_es_field="authorships.author.orcid",
    ),
    BooleanField(param="has_pmid", custom_es_field="ids.pmid"),
    BooleanField(param="has_pmcid", custom_es_field="ids.pmcid"),
    BooleanField(param="has_references", custom_es_field="referenced_works"),
    BooleanField(param="has_ngrams", custom_es_field="fulltext"),
    BooleanField(param="has_oa_accepted_or_published_version"),
    BooleanField(param="has_oa_submitted_version"),
    BooleanField(param="has_pdf_url", custom_es_field="locations.pdf_url"),
    BooleanField(
        param="has_raw_affiliation_string",
        custom_es_field="authorships.raw_affiliation_strings",
    ),
    BooleanField(
        param="is_corresponding", custom_es_field="authorships.is_corresponding"
    ),
    BooleanField(param="is_oa", alias="open_access.is_oa"),
    BooleanField(param="is_paratext"),
    BooleanField(param="is_retracted"),
    BooleanField(param="primary_location.source.has_issn"),
    BooleanField(
        param="primary_location.venue.has_issn",
        custom_es_field="primary_location.venue.issn",
    ),
    BooleanField(param="locations.is_oa"),
    BooleanField(param="open_access.is_oa"),
    BooleanField(param="open_access.any_repository_has_fulltext"),
    BooleanField(param="primary_location.is_oa"),
    DateField(
        param="from_created_date",
        custom_es_field="created_date",
    ),
    DateField(
        param="from_publication_date",
        custom_es_field="publication_date",
    ),
    DateTimeField(
        param="from_updated_date",
        custom_es_field="updated_date",
    ),
    DateField(param="publication_date"),
    DateField(
        param="to_publication_date",
        custom_es_field="publication_date",
    ),
    OpenAlexIDField(param="author.id", alias="authorships.author.id"),
    OpenAlexIDField(param="authorships.author.id"),
    OpenAlexIDField(param="authorships.institutions.id"),
    OpenAlexIDField(param="corresponding_author_ids"),
    OpenAlexIDField(param="corresponding_institution_ids"),
    OpenAlexIDField(param="best_oa_location.source.id"),
    OpenAlexIDField(param="best_oa_location.source.host_organization"),
    OpenAlexIDField(param="best_oa_location.source.host_organization_lineage"),
    OpenAlexIDField(param="cited_by"),
    OpenAlexIDField(param="cites", alias="referenced_works"),
    OpenAlexIDField(param="concept.id", alias="concepts.id"),
    OpenAlexIDField(param="concepts.id"),
    OpenAlexIDField(param="grants.funder", custom_es_field="grants.funder.keyword"),
    OpenAlexIDField(param="host_venue.id"),
    OpenAlexIDField(param="ids.openalex"),
    OpenAlexIDField(param="institution.id", alias="authorships.institutions.id"),
    OpenAlexIDField(param="institutions.id", alias="authorships.institutions.id"),
    OpenAlexIDField(param="journal", custom_es_field="primary_location.source.id"),
    OpenAlexIDField(param="locations.source.id"),
    OpenAlexIDField(
        param="locations.source.host_institution_lineage",
        custom_es_field="locations.source.host_organization_lineage",
    ),
    OpenAlexIDField(param="locations.source.host_organization"),
    OpenAlexIDField(param="locations.source.host_organization_lineage"),
    OpenAlexIDField(
        param="locations.source.publisher_lineage",
        custom_es_field="locations.source.host_organization_lineage",
    ),
    OpenAlexIDField(
        param="primary_location.source.host_institution_lineage",
        custom_es_field="primary_location.source.host_organization_lineage",
    ),
    OpenAlexIDField(param="primary_location.source.id"),
    OpenAlexIDField(param="primary_location.source.host_organization"),
    OpenAlexIDField(param="primary_location.source.host_organization_lineage"),
    OpenAlexIDField(
        param="primary_location.source.publisher_lineage",
        custom_es_field="primary_location.source.host_organization_lineage",
    ),
    OpenAlexIDField(param="openalex", custom_es_field="ids.openalex.lower"),
    OpenAlexIDField(param="openalex_id", alias="ids.openalex"),
    OpenAlexIDField(param="repository", custom_es_field="locations.source.id"),
    OpenAlexIDField(param="referenced_works"),
    OpenAlexIDField(param="related_to"),
    PhraseField(param="host_venue.publisher"),
    RangeField(param="apc_payment.price"),
    RangeField(param="apc_payment.price_usd"),
    RangeField(param="authors_count"),
    RangeField(param="cited_by_count"),
    RangeField(param="concepts_count"),
    RangeField(param="publication_year"),
    SearchField(param="abstract.search", custom_es_field="abstract"),
    SearchField(param="default.search", index="works"),
    SearchField(param="display_name.search"),
    SearchField(param="fulltext.search", custom_es_field="fulltext"),
    SearchField(
        param="raw_affiliation_string.search",
        custom_es_field="authorships.raw_affiliation_string",
    ),
    SearchField(param="title.search"),
    TermField(param="apc_payment.currency"),
    TermField(param="apc_payment.provenance"),
    TermField(param="author.orcid", alias="authorships.author.orcid"),
    TermField(param="authorships.author.orcid"),
    TermField(param="authorships.institutions.country_code"),
    TermField(
        param=f"authorships.institutions.continent",
        custom_es_field="authorships.institutions.country_code",
    ),
    TermField(param="authorships.institutions.ror"),
    TermField(param="authorships.institutions.type"),
    TermField(param="best_oa_location.source.issn"),
    TermField(
        param="best_oa_location.venue.issn",
        custom_es_field="best_oa_location.venue.issn.lower",
    ),
    TermField(param="best_oa_location.license"),
    TermField(param="best_oa_location.source.type"),
    TermField(
        param="best_oa_location.venue.type",
        custom_es_field="best_oa_location.venue.type.keyword",
    ),
    TermField(param="best_oa_location.version"),
    TermField(param="best_open_version", custom_es_field="locations.version"),
    TermField(param="concepts.wikidata"),
    TermField(param="display_name", custom_es_field="display_name.lower"),
    TermField(param="doi", alias="ids.doi"),
    TermField(param="doi_starts_with", custom_es_field="ids.doi"),
    TermField(param="ids.mag", custom_es_field="ids.mag"),
    TermField(param="ids.pmid", custom_es_field="ids.pmid"),
    TermField(param="ids.pmcid", custom_es_field="ids.pmcid"),
    TermField(
        param="institutions.country_code",
        alias="authorships.institutions.country_code",
    ),
    TermField(
        param="institutions.continent",
        alias="authorships.institutions.country_code",
    ),
    TermField(param="institutions.ror", alias="authorships.institutions.ror"),
    TermField(param="institutions.type", alias="authorships.institutions.type"),
    TermField(param="grants.award_id", custom_es_field="grants.award_id.keyword"),
    TermField(param="language", custom_es_field="language.keyword"),
    TermField(param="locations.source.issn"),
    TermField(
        param="locations.venue.issn", custom_es_field="locations.venue.issn.keyword"
    ),
    TermField(param="locations.license"),
    TermField(param="locations.source.type"),
    TermField(
        param="locations.venue.type", custom_es_field="locations.venue.type.keyword"
    ),
    TermField(param="locations.version"),
    TermField(param="mag", custom_es_field="ids.mag"),
    TermField(param="oa_status", alias="open_access.oa_status"),
    TermField(param="open_access.oa_status"),
    TermField(param="pmid", custom_es_field="ids.pmid"),
    TermField(param="pmcid", custom_es_field="ids.pmcid"),
    TermField(param="primary_location.license"),
    TermField(param="primary_location.source.issn"),
    TermField(param="primary_location.source.type"),
    TermField(param="primary_location.version"),
    TermField(param="type"),
    TermField(param="version", custom_es_field="locations.version"),
]

fields_dict = {f.param: f for f in fields}
