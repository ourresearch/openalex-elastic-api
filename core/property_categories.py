"""Coarse organizational category for each property (#441).

A purely *descriptive* grouping for every queryable property — "what kind of thing
is this?" (ids, citation, geo, open access, …). It mirrors the GUI's
`facetConfigs.js` categories so the registry, the API, and the OQL surfaces can
share one organizational lens instead of each maintaining its own. **Category has
no effect on query behavior** — nothing filters/sorts/groups by it; it only helps
humans and agents understand the contours of the ~837 registry properties.

Two deliberate properties of this metadata (Jason, 2026-06-10):

  * **Nullable / best-effort.** A property with no clear bucket resolves to
    ``None`` (honest — categorize later) rather than being forced into "other".
  * **No enforcement gate.** Unlike ``display_name`` (which the label-consistency
    gate polices), category is not required, the vocabulary is open, and drift
    against the GUI is tolerated (fix later if it matters).

Layered onto each ``Property`` in the properties **builder**
(`core.properties._build_entity_properties`), exactly like ``display_name`` /
``aliases`` (#381) — NOT on the engine ``Field``, because category is
organizational metadata, not engine behavior, and the same ``param`` can sit in a
different category per entity.

Vocabulary (#441) — the 11 ``facetConfigs.js`` categories…

    aboutness · author · citation · funder · geo · ids · institution ·
    investigator · "open access" · other · source

…plus ONE registry addition: ``dates`` (temporal fields that facetConfigs leaves
in "other" — publication/created/updated dates, award start/end, first pub year).
("citation" already holds every count/score/h-index field, so there is
intentionally no separate "metrics" bucket.)

Resolution order for a ``(entity_type, param)`` pair (see ``resolve_category``):
  1. per-entity override ``CATEGORY_OVERRIDES[entity_type][param]`` — authoritative,
     seeded verbatim from the live ``facetConfigs.js`` assignments (then the
     ``dates`` re-bucketing applied), so facet peers match the GUI exactly;
  2. global-by-param ``GLOBAL_CATEGORY_BY_PARAM[param]`` — for the per-entity
     injected facets (``works_count`` / ``cited_by_count`` → citation);
  3. name-pattern default ``_category_by_pattern(param)`` — best-effort for the
     non-facet long tail (id-shaped / date-shaped / geo / citation columns);
  4. ``None`` — no clear fit, left uncategorized on purpose.

Pure data + pure functions: no Flask / ES / DB imports, so it stays unit-testable
in a minimal venv and importable from the boot-time properties builder with no
side effects.
"""

from typing import Dict, Optional

# The category vocabulary (#441). Documentation only — NOT enforced (no closed-vocab
# gate, by design). "dates" is the one registry addition over facetConfigs' 11.
CATEGORY_VOCABULARY = (
    "aboutness",
    "author",
    "citation",
    "dates",
    "funder",
    "geo",
    "ids",
    "institution",
    "investigator",
    "open access",
    "other",
    "source",
)

# Per-entity injected facets in facetConfigs.js (works_count / cited_by_count are
# added for *every* entity at the bottom of facetConfigs()); applied to any entity
# carrying that param that has no explicit per-entity override above.
GLOBAL_CATEGORY_BY_PARAM: Dict[str, str] = {
    "works_count": "citation",
    "cited_by_count": "citation",
}

# Conservative name-pattern defaults for NON-facet registry properties (the bulk of
# the ~837 that have no facetConfigs peer). Only fires for high-confidence shapes;
# everything else stays None. Explicit overrides above always win.
_ID_PARAMS = {"doi", "issn", "issn_l", "orcid", "ror", "pmid", "pmcid", "mag", "id"}
_ID_HAS = {"has_doi", "has_orcid", "has_pmid", "has_pmcid", "has_issn"}
_ID_SUFFIXES = (".orcid", ".ror", ".issn", ".wikidata", ".pmid", ".pmcid", ".mag", ".doi")
_CITATION_PARAMS = {
    "cited_by_count",
    "works_count",
    "referenced_works_count",
    "fwci",
    "cited_by",
    "cites",
    "related_to",
}
_GEO_PARAMS = {"country_code", "country_codes", "continent"}


def _category_by_pattern(param: str) -> Optional[str]:
    """Best-effort category from a property name alone, or None if unsure."""
    # ids — OpenAlex/external identifiers and their presence flags
    if (
        param in _ID_PARAMS
        or param in _ID_HAS
        or param.startswith("ids.")
        or param.endswith(_ID_SUFFIXES)
    ):
        return "ids"
    # dates — any temporal column
    if "date" in param or param.endswith("_year") or param.endswith(".year"):
        return "dates"
    # geo — country / continent
    if (
        param in _GEO_PARAMS
        or param.endswith(".country_code")
        or param.endswith(".continent")
        or "country" in param
    ):
        return "geo"
    # citation — citation/impact metrics
    if param in _CITATION_PARAMS or param.startswith("summary_stats."):
        return "citation"
    return None


# Authoritative per-entity assignments, seeded verbatim from openalex-gui
# src/facetConfigs.js (the `category:` on each facetConfig), with the #441 `dates`
# re-bucketing applied (works/awards/sources temporal fields moved out of "other").
# facetConfigs calls work-types "types"; remapped here to the registry entity key
# "work-types" so the overrides actually land. Hand-editable going forward — this is
# a best-effort organizational seed, not a policed contract.
CATEGORY_OVERRIDES: Dict[str, Dict[str, str]] = {
    "authors": {
        "ids.openalex": "ids",
        "ids.orcid": "ids",
        "default.search": "other",
        "display_name": "other",
        "affiliations.institution.id": "institution",
        "affiliations.institution.type": "institution",
        "last_known_institutions.id": "institution",
        "last_known_institutions.country_code": "geo",
        "last_known_institutions.type": "institution",
        "has_orcid": "ids",
        "display_name_alternatives": "other",
        "summary_stats.h_index": "citation",
        "summary_stats.i10_index": "citation",
        "summary_stats.2yr_mean_citedness": "citation",
    },
    "awards": {
        "primary_topic.id": "aboutness",
        "primary_topic.subfield.id": "aboutness",
        "primary_topic.field.id": "aboutness",
        "primary_topic.domain.id": "aboutness",
        "institution_awarded.lineage": "institution",
        "institution_awarded.country_code": "geo",
        "display_name": "other",
        "amount": "other",
        "funder.id": "funder",
        "funding_type": "other",
        "start_date": "dates",
        "end_date": "dates",
        "start_year": "dates",
        "end_year": "dates",
        "funded_outputs_count": "other",
        "currency": "other",
        "doi": "ids",
        "id": "ids",
        "funder_award_id": "ids",
        "funder.doi": "funder",
        "funder.ror": "funder",
        "lead_investigator.affiliation.country": "investigator",
        "lead_investigator.affiliation.name": "investigator",
        "investigators": "investigator",
        "investigators.affiliation": "investigator",
        "provenance": "other",
        "description": "other",
        "landing_page_url": "ids",
        "funder_scheme": "funder",
    },
    "concepts": {
        "ids.openalex": "ids",
        "display_name.search": "other",
        "display_name": "other",
        "description": "other",
        "level": "other",
    },
    "continents": {
        "countries": "other",
        "display_name": "other",
    },
    "countries": {
        "description": "other",
        "display_name_alternatives": "other",
        "continent": "other",
        "is_global_south": "other",
        "display_name": "other",
    },
    "domains": {
        "description": "other",
        "display_name_alternatives": "other",
        "fields": "other",
        "siblings": "other",
        "display_name": "other",
    },
    "fields": {
        "description": "other",
        "display_name_alternatives": "other",
        "siblings": "other",
        "subfields": "other",
        "domain.id": "other",
        "display_name": "other",
    },
    "funders": {
        "ids.openalex": "ids",
        "default.search": "other",
        "display_name": "other",
        "ids.ror": "ids",
        "ids.wikidata": "ids",
        "ids.crossref": "ids",
        "ids.doi": "ids",
        "display_name.search": "other",
        "country_code": "geo",
        "is_global_south": "geo",
        "alternate_titles": "other",
        "description": "other",
        "homepage_url": "other",
        "awards_count": "citation",
        "works_count": "citation",
        "cited_by_count": "citation",
        "summary_stats.2yr_mean_citedness": "citation",
        "summary_stats.h_index": "citation",
        "summary_stats.i10_index": "citation",
    },
    "institution-types": {
        "description": "other",
        "display_name": "other",
    },
    "institutions": {
        "ids.openalex": "ids",
        "default.search": "other",
        "display_name": "other",
        "homepage_url": "other",
        "ids.ror": "ids",
        "display_name.search": "other",
        "country_code": "geo",
        "type": "other",
        "x_concepts.id": "other",
        "display_name_alternatives": "other",
        "parent_institutions": "other",
        "child_institutions": "other",
        "related_institutions": "other",
        "geo.city": "geo",
        "geo.region": "geo",
        "display_name_acronyms": "other",
        "summary_stats.2yr_mean_citedness": "citation",
        "summary_stats.h_index": "citation",
        "summary_stats.i10_index": "citation",
    },
    "keywords": {
        "display_name": "other",
    },
    "languages": {
        "display_name": "other",
    },
    "licenses": {
        "description": "other",
        "display_name": "other",
    },
    "locations": {
        "work_id": "other",
        "landing_page_url": "other",
        "pdf_url": "other",
        "native_id": "other",
        "native_id_namespace": "other",
        "id": "other",
        "provenance": "other",
        "title": "other",
        "type": "other",
        "source_name": "other",
        "publisher": "other",
        "source_id": "other",
        "is_oa": "other",
        "version": "other",
        "license": "other",
        "language": "other",
    },
    "oa-statuses": {
        "description": "other",
        "display_name": "other",
    },
    "publishers": {
        "ids.openalex": "ids",
        "display_name.search": "other",
        "alternate_titles": "other",
        "parent_publisher": "other",
        "country_codes": "other",
        "homepage_url": "other",
        "ids.ror": "ids",
        "ids.wikidata": "ids",
        "hierarchy_level": "other",
        "summary_stats.2yr_mean_citedness": "citation",
        "summary_stats.h_index": "citation",
        "summary_stats.i10_index": "citation",
        "display_name": "other",
    },
    "sdgs": {
        "description": "other",
        "display_name": "other",
    },
    "source-types": {
        "description": "other",
        "display_name": "other",
    },
    "sources": {
        "ids.openalex": "ids",
        "default.search": "other",
        "issn": "ids",
        "issn_l": "ids",
        "country_code": "geo",
        "first_publication_year": "dates",
        "homepage_url": "other",
        "display_name.search": "other",
        "display_name": "other",
        "publisher": "other",
        "type": "other",
        "topics.id": "aboutness",
        "apc_usd": "other",
        "is_oa": "open access",
        "is_in_doaj": "open access",
        "is_core": "other",
        "alternate_titles": "other",
        "summary_stats.2yr_mean_citedness": "citation",
        "summary_stats.h_index": "citation",
        "summary_stats.i10_index": "citation",
    },
    "subfields": {
        "description": "other",
        "display_name_alternatives": "other",
        "topics": "other",
        "siblings": "other",
        "field.id": "other",
        "domain.id": "other",
        "display_name": "other",
    },
    "topics": {
        "ids.openalex": "ids",
        "description": "other",
        "keywords": "other",
        "siblings": "other",
        "subfield.id": "other",
        "field.id": "other",
        "domain.id": "other",
        "display_name": "other",
    },
    "work-types": {
        "description": "other",
        "crossref_types": "other",
        "display_name": "other",
    },
    "works": {
        "ids.openalex": "ids",
        "doi": "ids",
        "concepts.id": "aboutness",
        "primary_topic.id": "aboutness",
        "keywords.id": "aboutness",
        "primary_topic.subfield.id": "aboutness",
        "primary_topic.field.id": "aboutness",
        "primary_topic.domain.id": "aboutness",
        "awards.id": "funder",
        "funders.id": "funder",
        "authorships.institutions.lineage": "institution",
        "authorships.institutions.ror": "ids",
        "authorships.author.id": "author",
        "authorships.author.orcid": "ids",
        "fulltext.search": "other",
        "title_and_abstract.search": "other",
        "display_name.search": "other",
        "title.search": "other",
        "raw_affiliation_strings.search": "other",
        "raw_affiliation_strings": "other",
        "doi_starts_with": "other",
        "display_name": "other",
        "has_abstract": "other",
        "authors_count": "author",
        "corresponding_author_ids": "author",
        "open_access.is_oa": "open access",
        "has_content.pdf": "open access",
        "best_oa_location.license": "open access",
        "open_access.oa_status": "open access",
        "best_oa_location.is_accepted": "open access",
        "best_oa_location.is_published": "open access",
        "apc_paid.value_usd": "other",
        "primary_location.source.id": "source",
        "locations.source.id": "source",
        "primary_location.source.issn": "ids",
        "primary_location.source.type": "source",
        "primary_location.source.is_in_doaj": "source",
        "primary_location.source.is_core": "source",
        "primary_location.source.is_oa": "source",
        "primary_location.source.publisher_lineage": "source",
        "authorships.countries": "geo",
        "countries_distinct_count": "geo",
        "institutions_distinct_count": "institution",
        "authorships.institutions.continent": "geo",
        "institutions.is_global_south": "geo",
        "authorships.institutions.type": "institution",
        "corresponding_institution_ids": "institution",
        "open_access.any_repository_has_fulltext": "source",
        "type": "other",
        "abstract": "other",
        "publication_year": "dates",
        "from_created_date": "dates",
        "from_updated_date": "dates",
        "apc_sum": "other",
        "cited_by_count_sum": "other",
        "publication_date": "dates",
        "has_doi": "ids",
        "indexed_in": "ids",
        "mag_only": "ids",
        "is_xpac": "other",
        "has_orcid": "ids",
        "has_pmid": "ids",
        "is_retracted": "other",
        "language": "geo",
        "sustainable_development_goals.id": "aboutness",
        "cited_by_count": "citation",
        "referenced_works_count": "citation",
        "fwci": "citation",
        "cited_by": "citation",
        "cites": "citation",
        "related_to": "citation",
    },
}


def resolve_category(entity_type: str, param: str) -> Optional[str]:
    """Resolve the organizational ``category`` for one property, or ``None``.

    Resolution order: per-entity override → global-by-param → name-pattern default
    → ``None``. ``None`` is a valid, intentional outcome (best-effort coverage).
    """
    override = CATEGORY_OVERRIDES.get(entity_type, {}).get(param)
    if override is not None:
        return override
    if param in GLOBAL_CATEGORY_BY_PARAM:
        return GLOBAL_CATEGORY_BY_PARAM[param]
    return _category_by_pattern(param)
