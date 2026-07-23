"""Works columns surfaced by the DOCUMENTED classic REST API (#420).

This is the `oxurl` half of each property's `supported_by` annotation (the `gui`
half is computed from the vendored `scripts/client_registry.json`). Moved
verbatim from `CURATED_EXTRA_WORKS_COLUMNS` in the retired
`scripts/regen_input_alias_columns.py` (#569/#572), which froze it into the
also-retired `query_translation/input_alias_columns.py` snapshot; now the
properties builder (`core.properties._build_entity_properties`) reads it
directly, so there is no generated middle layer left to drift.

Semantics (unchanged, Jason 2026-06-08): these are NOT user-facing vocabulary —
membership only grants the RAW column_id spelling in OQL's works fallback door
(never friendly words), so legacy documented-API params in oxurls keep
translating to OQL that re-parses. The standing friendly-name audit curates
these into `oql_lang._FIELDS` over time; once curated, a raw id parses via its
own alias, so this set shrinks toward empty. Works-only by design (#572 strict
GUI==OQL parity deleted the non-works extras). Curated by hand.
"""

OXURL_DOCUMENTED_WORKS_COLUMNS = frozenset({
    'abstract.search', 'apc_list.currency', 'apc_list.provenance', 'apc_list.value',
    'apc_list.value_usd', 'apc_paid.currency', 'apc_paid.provenance', 'apc_paid.value',
    'author.id', 'author.orcid', 'authorships.affiliations.institution_ids',
    'authorships.author.orcid', 'authorships.institutions.country_code',
    'authorships.institutions.id', 'authorships.institutions.is_global_south',
    'authorships.institutions.ror', 'authorships.is_corresponding',
    'best_oa_location.source.host_organization', 'best_oa_location.source.id',
    'best_oa_location.source.is_in_doaj', 'best_oa_location.source.issn',
    'best_oa_location.source.type', 'best_oa_location.version', 'best_open_version',
    'biblio.first_page', 'biblio.issue', 'biblio.last_page', 'biblio.volume',
    'cited_by', 'cites', 'concept.id', 'concepts.id', 'concepts.wikidata',
    'concepts_count', 'created_date', 'default.search', 'display_name', 'doi',
    'from_publication_date', 'fulltext_origin', 'has_content.grobid_xml',
    'has_fulltext', 'has_oa_accepted_or_published_version',
    'has_oa_submitted_version', 'has_pmcid', 'has_references', 'ids.mag',
    'indexed_in',
    'ids.openalex', 'ids.pmcid', 'ids.pmid', 'institutions.continent',
    'institutions.country_code', 'institutions.id', 'institutions.ror',
    'is_corresponding', 'is_oa', 'is_paratext', 'locations.is_accepted',
    'locations.is_oa', 'locations.is_published', 'locations.license',
    'locations.source.host_institution_lineage', 'locations.source.host_organization',
    'locations.source.host_organization_lineage', 'locations.source.is_core',
    'locations.source.is_in_doaj', 'locations.source.issn',
    'locations.source.publisher_lineage', 'locations.source.type',
    'locations.version', 'locations_count', 'oa_status',
    'primary_location.is_accepted', 'primary_location.is_oa',
    'primary_location.is_published', 'primary_location.license',
    'primary_location.source.has_issn', 'primary_location.source.host_organization',
    'primary_location.source.host_organization_lineage',
    'primary_location.source.issn', 'primary_location.version', 'publication_date',
    'referenced_works', 'to_created_date', 'to_publication_date', 'to_updated_date',
    'topics.domain.id', 'topics.field.id', 'topics.id', 'topics.subfield.id',
    'type_crossref', 'updated_date',
})
