"""Input-alias allowlist for raw works column_ids (oxjob #363).

OQL accepts a raw works-registry column_id as an INPUT alias (so oxurl-fluent
users / round-tripped renders of uncurated columns parse) — but ONLY for columns
that are surfaced to users somewhere: the openalex-gui facet picker
(`src/facetConfigs.js`, works `entityToFilter`) OR the documented API
(`docs` repo `api-entities/works/filter-works.md`). This deliberately EXCLUDES
the ~57 registry columns that are neither GUI-faceted nor documented — internal /
half-baked / redundant fields (`*.raw_type`, `*.license_id`, `institution_assertions.*`,
`has_embeddings`, percentile internals, `.search.exact` variants, …) that would
only confuse people. Coverage parity with the GUI + the documented API; nothing
more (Jason, 2026-06-08).

SNAPSHOT — regenerate when facetConfigs.js or filter-works.md change. The
standing friendly-name audit (oxjob: oql-friendly-name-audit) curates these into
`oql_lang._FIELDS` over time; once a column is curated its raw id parses via its
own alias and it no longer needs this fallback, so this set shrinks toward empty.

Source of truth = those two files; this is a generated mirror. Build it with the
facetConfigs works `entityToFilter` keys ∪ the documented filter tokens,
intersected with the live works property registry.
"""

# (facetConfigs.js works facets) ∪ (docs filter-works.md) ∩ works registry
INPUT_ALIAS_COLUMNS = frozenset({
    'abstract.search', 'apc_list.currency', 'apc_list.provenance', 'apc_list.value',
    'apc_list.value_usd', 'apc_paid.currency', 'apc_paid.provenance', 'apc_paid.value',
    'apc_paid.value_usd', 'author.id', 'author.orcid', 'authors_count',
    'authorships.affiliations.institution_ids', 'authorships.author.id',
    'authorships.author.orcid', 'authorships.countries', 'authorships.institutions.continent',
    'authorships.institutions.country_code', 'authorships.institutions.id',
    'authorships.institutions.is_global_south', 'authorships.institutions.lineage',
    'authorships.institutions.ror', 'authorships.institutions.type',
    'authorships.is_corresponding', 'awards.id', 'best_oa_location.is_accepted',
    'best_oa_location.is_published', 'best_oa_location.license',
    'best_oa_location.source.host_organization', 'best_oa_location.source.id',
    'best_oa_location.source.is_in_doaj', 'best_oa_location.source.issn',
    'best_oa_location.source.type', 'best_oa_location.version', 'best_open_version',
    'biblio.first_page', 'biblio.issue', 'biblio.last_page', 'biblio.volume', 'cited_by',
    'cited_by_count', 'cites', 'concept.id', 'concepts.id', 'concepts.wikidata',
    'concepts_count', 'corresponding_author_ids', 'corresponding_institution_ids',
    'countries_distinct_count', 'created_date', 'default.search', 'display_name',
    'display_name.search', 'doi', 'doi_starts_with', 'from_created_date',
    'from_publication_date', 'from_updated_date', 'fulltext.search', 'fulltext_origin',
    'funders.id', 'fwci', 'has_abstract', 'has_content.grobid_xml', 'has_content.pdf',
    'has_doi', 'has_fulltext', 'has_oa_accepted_or_published_version',
    'has_oa_submitted_version', 'has_orcid', 'has_pmcid', 'has_pmid', 'has_references',
    'ids.mag', 'ids.openalex', 'ids.pmcid', 'ids.pmid', 'indexed_in', 'institutions.continent',
    'institutions.country_code', 'institutions.id', 'institutions.is_global_south',
    'institutions.ror', 'institutions_distinct_count', 'is_corresponding', 'is_oa',
    'is_paratext', 'is_retracted', 'is_xpac', 'keywords.id', 'language',
    'locations.is_accepted', 'locations.is_oa', 'locations.is_published', 'locations.license',
    'locations.source.host_institution_lineage', 'locations.source.host_organization',
    'locations.source.host_organization_lineage', 'locations.source.id',
    'locations.source.is_core', 'locations.source.is_in_doaj', 'locations.source.issn',
    'locations.source.publisher_lineage', 'locations.source.type', 'locations.version',
    'locations_count', 'mag_only', 'oa_status', 'open_access.any_repository_has_fulltext',
    'open_access.is_oa', 'open_access.oa_status', 'primary_location.is_accepted',
    'primary_location.is_oa', 'primary_location.is_published', 'primary_location.license',
    'primary_location.source.has_issn', 'primary_location.source.host_organization',
    'primary_location.source.host_organization_lineage', 'primary_location.source.id',
    'primary_location.source.is_core', 'primary_location.source.is_in_doaj',
    'primary_location.source.is_oa', 'primary_location.source.issn',
    'primary_location.source.publisher_lineage', 'primary_location.source.type',
    'primary_location.version', 'primary_topic.domain.id', 'primary_topic.field.id',
    'primary_topic.id', 'primary_topic.subfield.id', 'publication_date', 'publication_year',
    'raw_affiliation_strings', 'raw_affiliation_strings.search', 'referenced_works',
    'referenced_works_count', 'related_to', 'sustainable_development_goals.id', 'title.search',
    'title_and_abstract.search', 'to_created_date', 'to_publication_date', 'to_updated_date',
    'topics.domain.id', 'topics.field.id', 'topics.id', 'topics.subfield.id', 'type',
    'type_crossref', 'updated_date',
})


# ---------------------------------------------------------------------------
# Non-works GUI-faceted allowlist (oxjob #406, increment 1b).
#
# The works allowlist above let a raw works column_id parse. #406 extends the
# same "GUI-parity" gate to the NON-works entities: a non-works column gains an
# OQL surface (via the entity-aware registry fallback in `oql_lang`) ONLY if the
# openalex-gui facet picker exposes it for that entity (`src/facetConfigs.js`,
# the facet's `entityToFilter`). This is Jason's GUI-parity lens (2026-06-09):
# engine-supported ⊋ GUI-faceted — we surface the GUI subset, not the full ~58
# engine-supported non-works filters (which include internal/half-baked columns).
#
# SNAPSHOT — regenerate when facetConfigs.js changes. Built as:
#   facetConfigs.js {key: entityToFilter==<ent>} ∩ live registry,
#   minus search/collection columns and the entity's own `ids.openalex`
#   (self-reference → use `openalex id`). Booleans are LISTED here but the
#   fallback skips them (their OQL render needs a curated `bool_true`/`bool_false`
#   sentence, so they're surfaced via `_FIELDS` _f(...) entries, not this fallback).
# Source of truth = facetConfigs.js; this is a generated mirror.
GUI_FACETED_COLUMNS_BY_ENTITY = {
    'authors': frozenset({
        'affiliations.institution.id', 'affiliations.institution.type', 'has_orcid',
        'last_known_institutions.country_code', 'last_known_institutions.id',
        'last_known_institutions.type', 'summary_stats.2yr_mean_citedness',
        'summary_stats.h_index', 'summary_stats.i10_index',
    }),
    'sources': frozenset({
        'apc_usd', 'country_code', 'first_publication_year', 'is_core', 'is_in_doaj',
        'is_oa', 'issn', 'issn_l', 'summary_stats.2yr_mean_citedness',
        'summary_stats.h_index', 'summary_stats.i10_index', 'topics.id', 'type',
    }),
    'institutions': frozenset({
        'country_code', 'lineage', 'summary_stats.2yr_mean_citedness',
        'summary_stats.h_index', 'summary_stats.i10_index', 'type', 'x_concepts.id',
    }),
    'funders': frozenset({
        'awards_count', 'cited_by_count', 'country_code', 'ids.crossref', 'ids.doi',
        'ids.ror', 'ids.wikidata', 'is_global_south', 'summary_stats.2yr_mean_citedness',
        'summary_stats.h_index', 'summary_stats.i10_index', 'works_count',
    }),
    'publishers': frozenset({
        'country_codes', 'hierarchy_level', 'ids.ror', 'ids.wikidata', 'parent_publisher',
        'summary_stats.2yr_mean_citedness', 'summary_stats.h_index', 'summary_stats.i10_index',
    }),
    'topics': frozenset({
        'domain.id', 'field.id', 'subfield.id',
    }),
}
