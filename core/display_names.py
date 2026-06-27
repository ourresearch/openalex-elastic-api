"""Canonical human display names + input aliases for properties (#381).

Single source of truth for the *word* a property is shown/typed as. Today that
word is hand-maintained across ≥4 drifting surfaces (GUI `facetConfigs.js`
`displayName`, OQL parse `oql_lang._FIELDS`, OQL render `COLUMN_DISPLAY_NAMES`,
docs) and the registry carried no human label at all. #381 makes the registry
the source of truth and projects it everywhere.

Two pieces of metadata per property:

  * ``display_name`` — the short canonical label/word (the chip word: "year",
    "full text"). NOT a sentence — that's ``Field.docstring`` (a separate, longer
    description already on the field).
  * ``aliases`` — alternate *input spellings of the column name itself* that a
    parser (OQL) should accept for this property, e.g. ``default`` ⇄ "anywhere",
    "any field". This is the OQL-parse alias list.

NOT the same as ``core.alternate_names.ALTERNATE_NAMES``. That table is a bag of
fuzzy *search tokens* for the filter-discovery search box (e.g. ``is_global_south``
→ ["asia", "africa", "india", …], with "full"/"text" as separate tokens). Those
are not parseable column-name spellings, so #381 keeps them as a distinct concept
— ``aliases`` here is the canonical column-spelling list, ``alternate_names`` stays
the search-token bag. (Verified 2026-06-06; the EXPLORE assumption that they were
one list was wrong.)

Resolution order for a (entity_type, param) pair:
  1. an explicit entry in ``DISPLAY_NAME_OVERRIDES[entity_type][param]``
     (the curated, intentional labels — Phase 2 seeds these by reconciling the
     existing GUI + OQL words), else
  2. ``(humanize(param), [])`` — a mechanical default so every one of the ~824
     properties has a sane label day one and the long tail needs no hand work.

This module is pure data + pure functions: no Flask, no ES, no DB imports, so it
stays unit-testable in a minimal venv and importable from the boot-time
properties builder without side effects.
"""

from typing import Dict, List, Tuple

# Suffixes on a search field's `param` that are mechanical, not part of the human
# label: `title_and_abstract.search` → label derived from `title_and_abstract`,
# and the `.exact` variant shares the base field's label. Stripped before
# humanizing so the default for a search field reads naturally.
_SEARCH_SUFFIXES = (".search.exact", ".search.no_stem", ".search")


def humanize(param: str) -> str:
    """Mechanical fallback label for a property `param`.

    Strips search-field suffixes, then turns dotted/underscored segments into a
    plain spaced phrase: ``publication_year`` → "publication year",
    ``title_and_abstract.search`` → "title and abstract". Intentional labels are
    set in ``DISPLAY_NAME_OVERRIDES`` instead; this only needs to be non-empty and
    not embarrassing for the long tail.
    """
    base = param
    for suffix in _SEARCH_SUFFIXES:
        if base.endswith(suffix):
            base = base[: -len(suffix)]
            break
    return base.replace(".", " ").replace("_", " ").strip()


# Curated overrides — Phase 2 reconciles the existing 261 GUI `displayName`s and
# ~35 OQL words into ONE canonical label + alias list per property. Keyed by
# entity_type (the OQO get_rows / ENTITY_FIELDS_MODULES key) → param. The same
# `param` legitimately differs per entity (e.g. works `display_name` → "title" vs
# authors `display_name` → "name"), so this MUST be entity-aware.
#
# Shape: DISPLAY_NAME_OVERRIDES[entity_type][param] = {
#     "display_name": "<short canonical label>",
#     "aliases": ["<alt column spelling>", ...],   # optional; OQL-parse aliases
# }
# Seeded 2026-06-06 by work_381_gen_overrides.py from the live registry × GUI
# facetConfigs.js × OQL _FIELDS join (evidence/RECONCILIATION.md). Policy: GUI
# label wins (else OQL word), lowercased with GUI acronym casing preserved,
# trailing parentheticals stripped. Hand-editable going forward — this is now
# the curated source of truth, not regenerated automatically. The works
# free-text trio (default/fulltext/title_and_abstract .search) is intentionally
# absent — owned by #374.
DISPLAY_NAME_OVERRIDES: Dict[str, Dict[str, dict]] = {
    'authors': {
        'affiliations.institution.id': {"display_name": 'past institutions'},
        'affiliations.institution.type': {"display_name": 'past institutions type'},
        'default.search': {"display_name": 'name'},
        'display_name': {"display_name": 'name'},
        'display_name_alternatives': {"display_name": 'observed names'},
        'has_orcid': {"display_name": 'has ORCID'},
        'ids.openalex': {"display_name": 'OpenAlex ID'},
        'last_known_institutions.country_code': {"display_name": 'institution country'},
        'last_known_institutions.id': {"display_name": 'institution'},
        'last_known_institutions.type': {"display_name": 'institution type'},
        'orcid': {"display_name": 'ORCID'},
        'summary_stats.2yr_mean_citedness': {"display_name": '2-year mean citedness'},
        'summary_stats.h_index': {"display_name": 'h-index'},
        'summary_stats.i10_index': {"display_name": 'i10-index'},
    },
    'awards': {
        'amount': {"display_name": 'amount'},
        'currency': {"display_name": 'currency'},
        'description': {"display_name": 'description'},
        'display_name': {"display_name": 'title'},
        'doi': {"display_name": 'DOI'},
        'end_date': {"display_name": 'end date'},
        'end_year': {"display_name": 'end year'},
        'funded_outputs_count': {"display_name": 'funded outputs count'},
        'funder.doi': {"display_name": 'funder DOI'},
        'funder.id': {"display_name": 'funder'},
        'funder.ror': {"display_name": 'funder ROR'},
        'funder_award_id': {"display_name": 'funder award ID'},
        'funder_scheme': {"display_name": 'funder scheme'},
        'funding_type': {"display_name": 'funding type'},
        'id': {"display_name": 'OpenAlex ID'},
        'institution_awarded.country_code': {"display_name": 'awarded country'},
        'institution_awarded.lineage': {"display_name": 'awarded institution'},
        'investigators': {"display_name": 'investigator'},
        'investigators.affiliation': {"display_name": 'institution'},
        'landing_page_url': {"display_name": 'landing page'},
        'lead_investigator.affiliation.country': {"display_name": 'investigator country'},
        'lead_investigator.affiliation.name': {"display_name": 'investigator affiliation'},
        'primary_topic.domain.id': {"display_name": 'domain'},
        'primary_topic.field.id': {"display_name": 'field'},
        'primary_topic.id': {"display_name": 'topic'},
        'primary_topic.subfield.id': {"display_name": 'subfield'},
        'provenance': {"display_name": 'provenance'},
        'start_date': {"display_name": 'start date'},
        'start_year': {"display_name": 'start year'},
    },
    'concepts': {
        'description': {"display_name": 'description'},
        'display_name': {"display_name": 'name'},
        'display_name.search': {"display_name": 'name search'},
        'ids.openalex': {"display_name": 'OpenAlex ID'},
        'level': {"display_name": 'level'},
    },
    'continents': {
        'countries': {"display_name": 'countries'},
        'display_name': {"display_name": 'name'},
    },
    'countries': {
        'continent': {"display_name": 'continent'},
        'description': {"display_name": 'description'},
        'display_name': {"display_name": 'name'},
        'display_name_alternatives': {"display_name": 'alternate names'},
        'is_global_south': {"display_name": 'global south'},
    },
    'domains': {
        'description': {"display_name": 'description'},
        'display_name': {"display_name": 'name'},
        'display_name_alternatives': {"display_name": 'alternate names'},
        'fields': {"display_name": 'child fields'},
        'siblings': {"display_name": 'sibling domains'},
    },
    'fields': {
        'description': {"display_name": 'description'},
        'display_name': {"display_name": 'name'},
        'display_name_alternatives': {"display_name": 'alternate names'},
        'domain.id': {"display_name": 'parent domain'},
        'siblings': {"display_name": 'sibling fields'},
        'subfields': {"display_name": 'child subfields'},
    },
    'funders': {
        'alternate_titles': {"display_name": 'alternate names'},
        'awards_count': {"display_name": 'awards count'},
        'country_code': {"display_name": 'country'},
        'default.search': {"display_name": 'name'},
        'description': {"display_name": 'description'},
        'display_name': {"display_name": 'name'},
        'display_name.search': {"display_name": 'name search'},
        'homepage_url': {"display_name": 'homepage URL'},
        'ids.crossref': {"display_name": 'CrossRef ID'},
        'ids.doi': {"display_name": 'DOI'},
        'ids.openalex': {"display_name": 'OpenAlex ID'},
        'ids.ror': {"display_name": 'ROR'},
        'ids.wikidata': {"display_name": 'wikidata ID'},
        'is_global_south': {"display_name": 'global south'},
        'summary_stats.2yr_mean_citedness': {"display_name": '2-year mean citedness'},
        'summary_stats.h_index': {"display_name": 'h-index'},
        'summary_stats.i10_index': {"display_name": 'i10-index'},
        'works_count': {"display_name": 'works count'},
    },
    'institution-types': {
        'description': {"display_name": 'description'},
        'display_name': {"display_name": 'name'},
    },
    'institutions': {
        'child_institutions': {"display_name": 'child institutions'},
        'country_code': {"display_name": 'country'},
        'default.search': {"display_name": 'name'},
        'display_name': {"display_name": 'name'},
        'display_name.search': {"display_name": 'name search'},
        'display_name_acronyms': {"display_name": 'acronyms'},
        'display_name_alternatives': {"display_name": 'alternate names'},
        'geo.city': {"display_name": 'city'},
        'geo.region': {"display_name": 'region'},
        'homepage_url': {"display_name": 'homepage'},
        'ids.openalex': {"display_name": 'OpenAlex ID'},
        'lineage': {"display_name": 'lineage'},
        'parent_institutions': {"display_name": 'parent institutions'},
        'related_institutions': {"display_name": 'related institutions'},
        'ror': {"display_name": 'ROR'},
        'summary_stats.2yr_mean_citedness': {"display_name": '2-year mean citedness'},
        'summary_stats.h_index': {"display_name": 'h-index'},
        'summary_stats.i10_index': {"display_name": 'i10-index'},
        'type': {"display_name": 'institution type'},
        'x_concepts.id': {"display_name": 'concepts'},
    },
    'keywords': {
        'display_name': {"display_name": 'name'},
    },
    'languages': {
        'display_name': {"display_name": 'name'},
    },
    'licenses': {
        'description': {"display_name": 'description'},
        'display_name': {"display_name": 'name'},
    },
    'locations': {
        'id': {"display_name": 'location ID'},
        'is_oa': {"display_name": 'is open access'},
        'landing_page_url': {"display_name": 'landing page URL'},
        'language': {"display_name": 'language'},
        'license': {"display_name": 'license'},
        'native_id': {"display_name": 'native ID'},
        'native_id_namespace': {"display_name": 'native ID namespace'},
        'pdf_url': {"display_name": 'PDF URL'},
        'provenance': {"display_name": 'provenance'},
        'publisher': {"display_name": 'publisher'},
        'source_id': {"display_name": 'source'},
        'source_name': {"display_name": 'source name'},
        'title': {"display_name": 'title'},
        'type': {"display_name": 'type'},
        'version': {"display_name": 'version'},
        'work_id': {"display_name": 'work'},
    },
    'publishers': {
        'alternate_titles': {"display_name": 'alternate names'},
        'country_codes': {"display_name": 'countries'},
        'display_name': {"display_name": 'name'},
        'display_name.search': {"display_name": 'name search'},
        'hierarchy_level': {"display_name": 'hierarchy level'},
        'homepage_url': {"display_name": 'homepage'},
        'ids.openalex': {"display_name": 'OpenAlex ID'},
        'ids.ror': {"display_name": 'ROR'},
        'ids.wikidata': {"display_name": 'wikidata ID'},
        'parent_publisher': {"display_name": 'parent publisher'},
        'summary_stats.2yr_mean_citedness': {"display_name": '2-year mean citedness'},
        'summary_stats.h_index': {"display_name": 'h-index'},
        'summary_stats.i10_index': {"display_name": 'i10-index'},
    },
    'sdgs': {
        'description': {"display_name": 'description'},
        'display_name': {"display_name": 'name'},
    },
    'source-types': {
        'description': {"display_name": 'description'},
        'display_name': {"display_name": 'name'},
    },
    'sources': {
        'alternate_titles': {"display_name": 'alternate names'},
        'apc_usd': {"display_name": 'article processing charge'},
        'country_code': {"display_name": 'country'},
        'default.search': {"display_name": 'name'},
        'display_name': {"display_name": 'name'},
        'display_name.search': {"display_name": 'title search'},
        'first_publication_year': {"display_name": 'first publication year'},
        'homepage_url': {"display_name": 'homepage'},
        'host_organization': {"display_name": 'publisher'},
        'ids.openalex': {"display_name": 'OpenAlex ID'},
        'is_core': {"display_name": 'CWTS core'},
        'is_in_doaj': {"display_name": 'DOAJ'},
        'is_oa': {"display_name": 'fully OA'},
        'issn': {"display_name": 'ISSN'},
        'issn_l': {"display_name": 'ISSN-L'},
        'summary_stats.2yr_mean_citedness': {"display_name": '2yr mean citedness'},
        'summary_stats.h_index': {"display_name": 'h-index'},
        'summary_stats.i10_index': {"display_name": 'i10-index'},
        'topics.id': {"display_name": 'topic'},
        'type': {"display_name": 'source type'},
    },
    'subfields': {
        'description': {"display_name": 'description'},
        'display_name': {"display_name": 'name'},
        'display_name_alternatives': {"display_name": 'alternate names'},
        'domain.id': {"display_name": 'domain'},
        'field.id': {"display_name": 'parent field'},
        'siblings': {"display_name": 'sibling subfields'},
        'topics': {"display_name": 'child topics'},
    },
    'topics': {
        'description': {"display_name": 'description'},
        'display_name': {"display_name": 'name'},
        'domain.id': {"display_name": 'domain'},
        'field.id': {"display_name": 'field'},
        'ids.openalex': {"display_name": 'OpenAlex ID'},
        'keywords': {"display_name": 'keywords'},
        'siblings': {"display_name": 'sibling topics'},
        'subfield.id': {"display_name": 'parent subfield', "aliases": ['subfield']},
    },
    'work-types': {
        'crossref_types': {"display_name": 'CrossRef types'},
        'description': {"display_name": 'description'},
        'display_name': {"display_name": 'name'},
    },
    'works': {
        'abstract': {"display_name": 'abstract'},
        'abstract.search': {"display_name": 'abstract'},
        'apc_paid.value_usd': {"display_name": 'estimated APC paid'},
        'apc_sum': {"display_name": 'APC sum'},
        'authors_count': {"display_name": 'authors count'},
        'authorships.author.id': {"display_name": 'author'},
        'authorships.author.orcid': {"display_name": 'ORCID', "aliases": ['author orcid']},
        'authorships.countries': {"display_name": 'country'},
        'authorships.institutions.continent': {"display_name": 'continent'},
        'authorships.institutions.lineage': {"display_name": 'institution'},
        'authorships.institutions.ror': {"display_name": 'ROR ID'},
        'authorships.institutions.type': {"display_name": 'institution type'},
        'awards.id': {"display_name": 'awards'},
        'best_oa_location.is_accepted': {"display_name": 'OA accepted'},
        'best_oa_location.is_published': {"display_name": 'OA published'},
        'best_oa_location.license': {"display_name": 'best OA license'},
        'best_oa_location.source.id': {"display_name": 'best OA source'},
        'best_oa_location.source.issn': {"display_name": 'best OA source ISSN'},
        'best_oa_location.source.type': {"display_name": 'best OA source type'},
        'biblio.first_page': {"display_name": 'first page'},
        'biblio.issue': {"display_name": 'issue'},
        'biblio.last_page': {"display_name": 'last page'},
        'biblio.volume': {"display_name": 'volume'},
        'citation_normalized_percentile.value': {"display_name": 'citation percentile by subfield'},
        'cited_by': {"display_name": 'cited by'},
        'cited_by_count_sum': {"display_name": 'citations sum'},
        'cited_by_percentile_year.min': {"display_name": 'citation percentile by year'},
        'cites': {"display_name": 'cites'},
        'concepts.id': {"display_name": 'concept'},
        'corresponding_author_ids': {"display_name": 'corresponding author'},
        'corresponding_institution_ids': {"display_name": 'corresponding institution'},
        'countries_distinct_count': {"display_name": 'countries count'},
        'country_code': {"display_name": 'country code'},
        'display_name': {"display_name": 'title'},
        'display_name.search': {"display_name": 'title', "aliases": ['display_name']},
        'doi': {"display_name": 'DOI'},
        'doi_starts_with': {"display_name": 'DOI prefix'},
        'domain.id': {"display_name": 'domain'},
        'from_created_date': {"display_name": 'created since date'},
        'from_updated_date': {"display_name": 'updated since date'},
        'fulltext.search': {"display_name": 'full text', "aliases": ['any field', 'anywhere', 'default', 'default.search', 'full text', 'fulltext']},
        'funders.id': {"display_name": 'funder', "aliases": ['grants.funder']},
        'fwci': {"display_name": 'FWCI'},
        'has_abstract': {"display_name": 'has abstract'},
        'has_content.pdf': {"display_name": 'PDF-linked'},
        'has_doi': {"display_name": 'has DOI'},
        'has_orcid': {"display_name": 'has ORCID'},
        'has_pmid': {"display_name": 'PubMed'},
        'ids.mag': {"display_name": 'MAG ID'},
        'ids.openalex': {"display_name": 'OpenAlex ID'},
        'ids.pmcid': {"display_name": 'PMCID'},
        'ids.pmid': {"display_name": 'PMID'},
        'indexed_in': {"display_name": 'indexed in'},
        'institutions.display_name.search': {"display_name": 'institution name'},
        'institutions.is_global_south': {"display_name": 'global south'},
        'institutions_distinct_count': {"display_name": 'institutions count'},
        'is_retracted': {"display_name": 'retracted'},
        # DEPRECATED filter (#498): `is_xpac` is `unlisted` (dropped from public
        # /properties) — use the `corpus` selector instead (#481). This label is
        # kept only so the still-live column stays consistent with the GUI's
        # surviving facet (keeps the label-consistency gate green). Don't advertise
        # is_xpac as a filter. See works/fields.py for the full deprecation banner.
        'is_xpac': {"display_name": 'extended index'},
        'keywords.id': {"display_name": 'keyword'},
        'language': {"display_name": 'language'},
        'last_known_institutions.country_code': {"display_name": 'author country'},
        'last_known_institutions.id': {"display_name": 'last known institution'},
        'locations.license': {"display_name": 'any location license'},
        'locations.source.id': {"display_name": 'any location source'},
        'locations.source.issn': {"display_name": 'any location source ISSN'},
        'locations.source.type': {"display_name": 'any location source type'},
        'locations.version': {"display_name": 'any location version'},
        'mag_only': {"display_name": 'MAG-only'},
        'open_access.any_repository_has_fulltext': {"display_name": 'has repository fulltext'},
        'open_access.is_oa': {"display_name": 'open access'},
        'open_access.oa_status': {"display_name": 'open access status', "aliases": ['OA status']},
        'primary_location.license': {"display_name": 'license'},
        'primary_location.version': {"display_name": 'primary version'},
        'primary_location.source.id': {"display_name": 'source'},
        'primary_location.source.is_core': {"display_name": 'CWTS core'},
        'primary_location.source.is_in_doaj': {"display_name": 'DOAJ'},
        'primary_location.source.is_oa': {"display_name": 'OA source'},
        'primary_location.source.issn': {"display_name": 'ISSN'},
        'primary_location.source.publisher_lineage': {"display_name": 'publisher'},
        'primary_location.source.type': {"display_name": 'source type'},
        'primary_topic.domain.id': {"display_name": 'domain'},
        'primary_topic.field.id': {"display_name": 'field'},
        'primary_topic.id': {"display_name": 'topic'},
        'primary_topic.subfield.id': {"display_name": 'subfield'},
        'publication_date': {"display_name": 'date'},
        'publication_year': {"display_name": 'year'},
        'raw_affiliation_strings': {"display_name": 'exact raw affiliation'},
        'raw_affiliation_strings.search': {"display_name": 'raw affiliation', "aliases": ['affiliation', 'raw affiliation string']},
        'raw_author_name.search': {"display_name": 'byline', "aliases": ['raw author name']},
        'related_to': {"display_name": 'related to'},
        'sustainable_development_goals.id': {"display_name": 'SDG', "aliases": ['sustainable development goal', 'sustainable development goals']},
        'title.search': {"display_name": 'title'},
        'title_and_abstract.search': {"display_name": 'title/abstract', "aliases": ['title & abstract', 'title and abstract', 'title&abstract', 'title_and_abstract']},
        'topics.id': {"display_name": 'topics'},
        'type': {"display_name": 'type'},
    },
}


# Thread B (#446, 2026-06-12): full friendly-name audit — curate the remaining
# `humanize()` path-dump fallbacks on filter/search props (ACC #5). Kept as a
# separate block (merged below) so the audit is reviewable in one place. Only
# genuinely-ugly labels are curated; clear auto-names (counts, dates, plain
# has_<word>/is_<word>, gui-facet labels) are intentionally left to humanize().
# Conventions: location matrix-scope (primary unmarked / "(any location)" /
# "best OA …", per #1.10); acronyms upper-cased; awards.* → "award …" (Jason
# 2026-06-12). A few entries (e.g. authorships.institutions.lineage) intentionally
# REPLACE a prior label (the bare "institution" mis-sat on .lineage; it now names
# the .id, the institution-filter survivor of the #446 dedup).
_THREAD_B_OVERRIDES: Dict[str, Dict[str, dict]] = {
    'works': {
        # APC
        'apc_list.value': {"display_name": 'APC list price'},
        'apc_list.value_usd': {"display_name": 'APC list price (USD)'},
        'apc_list.currency': {"display_name": 'APC list currency'},
        'apc_list.provenance': {"display_name": 'APC list provenance'},
        'apc_paid.value': {"display_name": 'APC paid'},
        'apc_paid.currency': {"display_name": 'APC paid currency'},
        'apc_paid.provenance': {"display_name": 'APC paid provenance'},
        # authorships / institution (incl. #446 merge-survivors)
        # The gui's "institution" facet is the lineage filter (institution + parents);
        # keep it. The #446 dedup survivor `.id` is the exact-match filter — label it
        # distinctly instead of leaving the "authorships institutions id" path-dump.
        'authorships.institutions.id': {"display_name": 'institution (exact)'},
        'authorships.institutions.country_code': {"display_name": 'institution country'},
        'authorships.institutions.is_global_south': {"display_name": 'institution is in Global South'},
        'authorships.affiliations.institution_ids': {"display_name": 'affiliation institution'},
        'authorships.is_corresponding': {"display_name": 'is corresponding author'},
        'authorships.raw_orcid': {"display_name": 'raw ORCID'},
        # asserted institutions
        'institution_assertions.id': {"display_name": 'asserted institution'},
        'institution_assertions.country_code': {"display_name": 'asserted institution country'},
        'institution_assertions.lineage': {"display_name": 'asserted institution lineage'},
        'institution_assertions.ror': {"display_name": 'asserted institution ROR'},
        'institution_assertions.type': {"display_name": 'asserted institution type'},
        # awards (grants)
        'awards.funder_id': {"display_name": 'award funder'},
        'awards.funder_display_name': {"display_name": 'award funder name'},
        'awards.funder_award_id': {"display_name": 'award ID'},
        'awards.doi': {"display_name": 'award DOI'},
        # location matrix-scope (primary unmarked / "(any location)" / "best OA …")
        'primary_location.is_oa': {"display_name": 'primary OA'},
        'locations.is_oa': {"display_name": 'any location OA'},
        'best_oa_location.is_oa': {"display_name": 'best OA location is open access'},
        'primary_location.is_accepted': {"display_name": 'primary accepted'},
        'locations.is_accepted': {"display_name": 'any location accepted'},
        'primary_location.is_published': {"display_name": 'primary published'},
        'locations.is_published': {"display_name": 'any location published'},
        'primary_location.landing_page_url': {"display_name": 'landing page URL'},
        'locations.landing_page_url': {"display_name": 'landing page URL (any location)'},
        'best_oa_location.landing_page_url': {"display_name": 'best OA landing page URL'},
        'primary_location.raw_type': {"display_name": 'location type (raw)'},
        'locations.raw_type': {"display_name": 'location type, raw (any location)'},
        'best_oa_location.raw_type': {"display_name": 'best OA location type (raw)'},
        'primary_location.source.has_issn': {"display_name": 'has ISSN'},
        'locations.source.has_issn': {"display_name": 'source has ISSN (any location)'},
        'primary_location.source.host_organization': {"display_name": 'host organization'},
        'locations.source.host_organization': {"display_name": 'host organization (any location)'},
        'best_oa_location.source.host_organization': {"display_name": 'best OA host organization'},
        'primary_location.source.host_organization_lineage': {"display_name": 'host organization lineage'},
        'locations.source.host_organization_lineage': {"display_name": 'host organization lineage (any location)'},
        'best_oa_location.source.host_organization_lineage': {"display_name": 'best OA host organization lineage'},
        'locations.source.is_in_doaj': {"display_name": 'any location DOAJ'},
        'best_oa_location.source.is_in_doaj': {"display_name": 'best OA source DOAJ'},
        'locations.source.is_oa': {"display_name": 'source is OA (any location)'},
        'best_oa_location.source.is_oa': {"display_name": 'best OA source is OA'},
        'locations.source.is_core': {"display_name": 'any location CWTS core'},
        'best_oa_location.version': {"display_name": 'best OA version'},
        # citation / SDG / misc
        'citation_normalized_percentile.is_in_top_1_percent': {"display_name": 'top 1% cited'},
        'citation_normalized_percentile.is_in_top_10_percent': {"display_name": 'top 10% cited'},
        'cited_by_percentile_year.max': {"display_name": 'citation percentile (max)'},
        'sustainable_development_goals.score': {"display_name": 'SDG score'},
        'concepts.wikidata': {"display_name": 'concept Wikidata ID'},
        'topics.domain.id': {"display_name": 'domain'},
        'topics.field.id': {"display_name": 'field'},
        'topics.subfield.id': {"display_name": 'subfield'},
        'type_crossref': {"display_name": 'Crossref type'},
        'has_pmcid': {"display_name": 'has PMCID'},
    },
    'authors': {
        'affiliations.institution.country_code': {"display_name": 'affiliation institution country'},
        'affiliations.institution.lineage': {"display_name": 'affiliation institution lineage'},
        'affiliations.institution.ror': {"display_name": 'affiliation institution ROR'},
        'last_known_institutions.continent': {"display_name": 'last institution continent'},
        'last_known_institutions.is_global_south': {"display_name": 'last institution is in Global South'},
        'last_known_institutions.lineage': {"display_name": 'last institution lineage'},
        'last_known_institutions.ror': {"display_name": 'last institution ROR'},
        'parsed_longest_name.first': {"display_name": 'first name'},
        'parsed_longest_name.middle': {"display_name": 'middle name'},
        'parsed_longest_name.last': {"display_name": 'last name'},
        'parsed_longest_name.suffix': {"display_name": 'name suffix'},
        'topic_share.id': {"display_name": 'topic share'},
        'topics.id': {"display_name": 'topic'},
        'x_concepts.id': {"display_name": 'concept (legacy)'},
    },
    'institutions': {
        'repositories.host_organization': {"display_name": 'repository host organization'},
        'repositories.host_organization_lineage': {"display_name": 'repository host organization lineage'},
        'repositories.id': {"display_name": 'repository'},
        'roles.id': {"display_name": 'role'},
        'topic_share.id': {"display_name": 'topic share'},
        'topics.id': {"display_name": 'topic'},
    },
    'sources': {
        'apc_prices.price': {"display_name": 'APC price'},
        'apc_prices.currency': {"display_name": 'APC currency'},
        'host_organization.id': {"display_name": 'host organization'},
        'host_organization_lineage': {"display_name": 'host organization lineage'},
        'ids.mag': {"display_name": 'MAG ID'},
        'topic_share.id': {"display_name": 'topic share'},
        'x_concepts.id': {"display_name": 'concept (legacy)'},
    },
    'concepts': {
        'ancestors.id': {"display_name": 'ancestor concept'},
        'summary_stats.2yr_mean_citedness': {"display_name": '2-year mean citedness'},
        'summary_stats.h_index': {"display_name": 'h-index'},
        'summary_stats.i10_index': {"display_name": 'i10 index'},
        'wikidata_id': {"display_name": 'Wikidata ID'},
    },
    'publishers': {
        'roles.id': {"display_name": 'role'},
    },
    'funders': {
        'roles.id': {"display_name": 'role'},
    },
    'domains': {
        'fields.id': {"display_name": 'field'},
    },
    'fields': {
        'subfields.id': {"display_name": 'subfield'},
    },
    'subfields': {
        'topics.id': {"display_name": 'topic'},
    },
}

# Merge the audit block in (it WINS over any prior entry — intentional for the few
# relabels like authorships.institutions.lineage).
for _ent, _ov in _THREAD_B_OVERRIDES.items():
    DISPLAY_NAME_OVERRIDES.setdefault(_ent, {}).update(_ov)


# Global, entity-agnostic overrides keyed by ``param`` only. For properties whose
# canonical label is the SAME across every entity that carries them, this avoids
# repeating the same entry under 20+ entity keys. A per-entity override in
# DISPLAY_NAME_OVERRIDES still wins (more specific), so an entity can opt out.
#
# The citation/reference family is named to match the field consensus and to keep
# every filter's name distinct from its neighbours (#381 research, 2026-06-07):
#   * the COUNT is "citation count" (singular) — what Semantic Scholar
#     (citationCount), iCite (citation_count), Europe PMC (citedByCount) call it;
#   * "cited by" / "cites" stay reserved for the RELATIONSHIP filters (no system
#     reuses one word for both a count and a relationship);
#   * outgoing references use the near-universal word "references", its count
#     "reference count" (cf. Semantic Scholar referenceCount, WoS "Cited Reference
#     Count"). Old spellings are kept as OQL-parse aliases for back-compat.
GLOBAL_DISPLAY_NAME_OVERRIDES: Dict[str, dict] = {
    'cited_by_count': {"display_name": 'citation count', "aliases": ['citations', 'cited by count']},
    'referenced_works': {"display_name": 'references', "aliases": ['referenced works']},
    'referenced_works_count': {"display_name": 'reference count', "aliases": ['references count']},
    # oxjob #430 — text.search is the honest non-works canonical for the broad
    # per-entity search (name + alternate names + description/keywords). Same label
    # on every non-works entity, so it lives here, not per-entity. NOT "name": on
    # concepts/funders/awards/topics it also searches descriptions/keywords.
    # `default` / `default.search` are the demoted alternate keys/spellings.
    'text.search': {"display_name": 'text', "aliases": ['anywhere', 'any field', 'default', 'default.search', 'text']},
}


def resolve_display_name(entity_type: str, param: str) -> Tuple[str, List[str]]:
    """Resolve ``(display_name, aliases)`` for one property.

    Resolution order: per-entity override → global-by-param override →
    ``(humanize(param), [])``. Always returns a non-empty ``display_name`` for any
    non-empty ``param``.
    """
    override = (DISPLAY_NAME_OVERRIDES.get(entity_type, {}).get(param)
                or GLOBAL_DISPLAY_NAME_OVERRIDES.get(param))
    if override:
        display_name = override.get("display_name") or humanize(param)
        aliases = list(override.get("aliases", []))
        return display_name, aliases
    return humanize(param), []
