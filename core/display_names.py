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
        'has_orcid': {"display_name": 'has an ORCID'},
        'ids.openalex': {"display_name": 'author'},
        'last_known_institutions.country_code': {"display_name": 'institution country'},
        'last_known_institutions.id': {"display_name": 'institution'},
        'last_known_institutions.type': {"display_name": 'institution type'},
        'summary_stats.2yr_mean_citedness': {"display_name": '2-year mean citedness'},
        'summary_stats.h_index': {"display_name": 'h-index'},
        'summary_stats.i10_index': {"display_name": 'i10-index'},
    },
    'awards': {
        'funder.id': {"display_name": 'funder'},
        'id': {"display_name": 'openalex ID'},
        'institution_awarded.country_code': {"display_name": 'awarded country'},
        'institution_awarded.lineage': {"display_name": 'awarded institution'},
        'lead_investigator.affiliation.country': {"display_name": 'investigator country'},
        'lead_investigator.affiliation.name': {"display_name": 'investigator affiliation'},
        'primary_topic.domain.id': {"display_name": 'domain'},
        'primary_topic.field.id': {"display_name": 'field'},
        'primary_topic.id': {"display_name": 'topic'},
        'primary_topic.subfield.id': {"display_name": 'subfield'},
    },
    'concepts': {
        'display_name': {"display_name": 'name'},
        'display_name.search': {"display_name": 'name search'},
        'ids.openalex': {"display_name": 'concept'},
    },
    'continents': {
        'display_name': {"display_name": 'name'},
    },
    'countries': {
        'display_name': {"display_name": 'name'},
    },
    'domains': {
        'display_name': {"display_name": 'name'},
    },
    'fields': {
        'display_name': {"display_name": 'name'},
        'domain.id': {"display_name": 'domain'},
    },
    'funders': {
        'country_code': {"display_name": 'country'},
        'default.search': {"display_name": 'name'},
        'display_name': {"display_name": 'name'},
        'display_name.search': {"display_name": 'name search'},
        'ids.crossref': {"display_name": 'crossref ID'},
        'ids.doi': {"display_name": 'DOI'},
        'ids.openalex': {"display_name": 'funder'},
        'ids.ror': {"display_name": 'ROR'},
        'ids.wikidata': {"display_name": 'wikidata ID'},
        'is_global_south': {"display_name": 'global south'},
        'summary_stats.2yr_mean_citedness': {"display_name": '2-year mean citedness'},
        'summary_stats.h_index': {"display_name": 'h-index'},
        'summary_stats.i10_index': {"display_name": 'i10-index'},
    },
    'institution-types': {
        'display_name': {"display_name": 'name'},
    },
    'institutions': {
        'country_code': {"display_name": 'country'},
        'default.search': {"display_name": 'name'},
        'display_name': {"display_name": 'name'},
        'display_name.search': {"display_name": 'name search'},
        'ids.openalex': {"display_name": 'institution'},
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
        'display_name': {"display_name": 'name'},
    },
    'locations': {
        'id': {"display_name": 'location ID'},
        'is_oa': {"display_name": 'is open access'},
        'source_id': {"display_name": 'source'},
        'work_id': {"display_name": 'work'},
    },
    'publishers': {
        'country_codes': {"display_name": 'countries'},
        'display_name': {"display_name": 'name'},
        'display_name.search': {"display_name": 'name search'},
        'ids.openalex': {"display_name": 'publisher'},
        'ids.ror': {"display_name": 'ROR'},
        'ids.wikidata': {"display_name": 'wikidata ID'},
        'summary_stats.2yr_mean_citedness': {"display_name": '2-year mean citedness'},
        'summary_stats.h_index': {"display_name": 'h-index'},
        'summary_stats.i10_index': {"display_name": 'i10-index'},
    },
    'sdgs': {
        'display_name': {"display_name": 'name'},
    },
    'source-types': {
        'display_name': {"display_name": 'name'},
    },
    'sources': {
        'apc_usd': {"display_name": 'article processing charge'},
        'country_code': {"display_name": 'country'},
        'default.search': {"display_name": 'name'},
        'display_name': {"display_name": 'name'},
        'display_name.search': {"display_name": 'title search'},
        'ids.openalex': {"display_name": 'source'},
        'is_core': {"display_name": 'CWTS core source'},
        'is_in_doaj': {"display_name": 'in DOAJ'},
        'is_oa': {"display_name": 'fully open access'},
        'issn_l': {"display_name": 'ISSN-L'},
        'summary_stats.2yr_mean_citedness': {"display_name": '2yr mean citedness'},
        'summary_stats.h_index': {"display_name": 'h-index'},
        'summary_stats.i10_index': {"display_name": 'i10-index'},
        'topics.id': {"display_name": 'topic'},
        'type': {"display_name": 'source type'},
    },
    'subfields': {
        'display_name': {"display_name": 'name'},
        'domain.id': {"display_name": 'domain'},
        'field.id': {"display_name": 'field'},
    },
    'topics': {
        'display_name': {"display_name": 'name'},
        'domain.id': {"display_name": 'domain'},
        'field.id': {"display_name": 'field'},
        'ids.openalex': {"display_name": 'topic'},
        'subfield.id': {"display_name": 'subfield'},
    },
    'work-types': {
        'display_name': {"display_name": 'name'},
    },
    'works': {
        'apc_paid.value_usd': {"display_name": 'APC paid'},
        'authorships.author.id': {"display_name": 'author'},
        'authorships.author.orcid': {"display_name": 'ORCID', "aliases": ['author orcid']},
        'authorships.countries': {"display_name": 'country'},
        'authorships.institutions.continent': {"display_name": 'continent'},
        'authorships.institutions.lineage': {"display_name": 'institution'},
        'authorships.institutions.ror': {"display_name": 'ROR ID'},
        'authorships.institutions.type': {"display_name": 'institution type'},
        'awards.id': {"display_name": 'awards'},
        'best_oa_location.is_accepted': {"display_name": 'open access accepted'},
        'best_oa_location.is_published': {"display_name": 'open access published'},
        'best_oa_location.license': {"display_name": 'license'},
        'citation_normalized_percentile.value': {"display_name": 'citation percentile'},
        'cited_by_count': {"display_name": 'citation count', "aliases": ['cited by count']},
        'cited_by_percentile_year.min': {"display_name": 'citation percentile'},
        'concepts.id': {"display_name": 'concept'},
        'corresponding_author_ids': {"display_name": 'corresponding author'},
        'corresponding_institution_ids': {"display_name": 'corresponding institution'},
        'countries_distinct_count': {"display_name": 'countries count'},
        'display_name': {"display_name": 'title'},
        'display_name.search': {"display_name": 'title', "aliases": ['display_name']},
        'doi_starts_with': {"display_name": 'DOI prefix'},
        'from_created_date': {"display_name": 'created since date'},
        'from_updated_date': {"display_name": 'updated since date'},
        'funders.id': {"display_name": 'funder', "aliases": ['grants.funder']},
        'has_abstract': {"display_name": 'abstract available'},
        'has_content.pdf': {"display_name": 'linked to a PDF'},
        'has_doi': {"display_name": 'has a DOI'},
        'has_orcid': {"display_name": 'indexed by ORCID'},
        'has_pmid': {"display_name": 'indexed by PubMed'},
        'ids.openalex': {"display_name": 'openalex id'},
        'institutions.is_global_south': {"display_name": 'from global south'},
        'institutions_distinct_count': {"display_name": 'institutions count'},
        'is_retracted': {"display_name": 'retracted'},
        'is_xpac': {"display_name": 'new in data version 2'},
        'keywords.id': {"display_name": 'keyword'},
        'locations.license': {"display_name": 'license'},
        'locations.source.id': {"display_name": 'source'},
        'mag_only': {"display_name": 'indexed by MAG only'},
        'open_access.any_repository_has_fulltext': {"display_name": 'has repository fulltext'},
        'open_access.is_oa': {"display_name": 'open access'},
        'open_access.oa_status': {"display_name": 'open access status'},
        'primary_location.source.id': {"display_name": 'source'},
        'primary_location.source.is_core': {"display_name": 'CWTS core source'},
        'primary_location.source.is_in_doaj': {"display_name": 'indexed by DOAJ'},
        'primary_location.source.is_oa': {"display_name": 'in OA source'},
        'primary_location.source.issn': {"display_name": 'ISSN'},
        'primary_location.source.publisher_lineage': {"display_name": 'publisher'},
        'primary_location.source.type': {"display_name": 'source type'},
        'primary_topic.domain.id': {"display_name": 'domain'},
        'primary_topic.field.id': {"display_name": 'field'},
        'primary_topic.id': {"display_name": 'topic'},
        'primary_topic.subfield.id': {"display_name": 'subfield'},
        'publication_date': {"display_name": 'date'},
        'publication_year': {"display_name": 'year'},
        'raw_affiliation_strings': {"display_name": 'raw affiliation'},
        'raw_affiliation_strings.search': {"display_name": 'raw affiliation', "aliases": ['affiliation', 'raw affiliation string']},
        'raw_author_name.search': {"display_name": 'byline', "aliases": ['raw author name']},
        'referenced_works_count': {"display_name": 'references count'},
        'sustainable_development_goals.id': {"display_name": 'sustainable development goal', "aliases": ['sustainable development goals']},
        'topics.id': {"display_name": 'topics'},
    },
}


def resolve_display_name(entity_type: str, param: str) -> Tuple[str, List[str]]:
    """Resolve ``(display_name, aliases)`` for one property.

    Curated override wins; otherwise ``(humanize(param), [])``. Always returns a
    non-empty ``display_name`` for any non-empty ``param``.
    """
    override = DISPLAY_NAME_OVERRIDES.get(entity_type, {}).get(param)
    if override:
        display_name = override.get("display_name") or humanize(param)
        aliases = list(override.get("aliases", []))
        return display_name, aliases
    return humanize(param), []
