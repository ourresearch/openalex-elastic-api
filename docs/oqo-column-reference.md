# OQO Column Reference

This document provides a reference of valid `column_id` values for use in OQO (OpenAlex Query Object) filters, organized by entity type.

## Overview

The `column_id` in a LeafFilter specifies what field to filter on. These map to:
- **URL format**: The filter parameter key (e.g., `filter=type:article`)
- **OQL format**: The human-readable field name (e.g., `type is Article [types/article]`)

### ID Format

All entity IDs in OQO use a normalized format: `entityName/id`

**Examples:**
- Native entities: `institutions/I136199984`, `authors/A5023888391`, `works/W2741809807`
- Non-native entities: `countries/de`, `sdgs/13`, `types/article`, `oa-statuses/gold`

---

## Entity Types

### Native Entities (OpenAlex-minted IDs)

| Entity | ID Prefix | Example ID (normalized) | Description |
|--------|-----------|------------------------|-----------|
| works | W | `works/W2741809807` | Scholarly papers, books, datasets |
| authors | A | `authors/A5023888391` | Creators of scholarly works |
| institutions | I | `institutions/I136199984` | Universities and research centers |
| sources | S | `sources/S137773608` | Journals, conferences, repositories |
| publishers | P | `publishers/P4310319908` | Publishing organizations |
| funders | F | `funders/F4320332161` | Research funding organizations |
| topics | T | `topics/T10012` | AI-assigned research topics |
| concepts | C | `concepts/C86803240` | Legacy topic classification (deprecated) |
| awards | G | `awards/G5453342221` | Research grants and awards |

### Non-Native Entities (External IDs)

| Entity | ID Format | Example (normalized) | Description |
|--------|-----------|---------------------|-------------|
| countries | ISO 3166-1 alpha-2 | `countries/us` | Country codes |
| continents | Numeric | `continents/1` | Continent identifiers |
| domains | Numeric | `domains/1` | Top-level topic domains |
| fields | Numeric | `fields/12` | Topic fields |
| subfields | Numeric | `subfields/1201` | Topic subfields |
| sdgs | Numeric (1-17) | `sdgs/13` | UN Sustainable Development Goals |
| languages | ISO 639-1 | `languages/en` | Language codes |
| licenses | Slug | `licenses/cc-by` | License identifiers |
| types | Slug | `types/article` | Work type identifiers |
| source-types | Slug | `source-types/journal` | Source type identifiers |
| institution-types | Slug | `institution-types/education` | Institution type identifiers |
| oa-statuses | Slug | `oa-statuses/gold` | Open Access status identifiers |
| keywords | Slug | `keywords/keyword-123` | Keyword identifiers |
| locations | Slug | `locations/loc-123` | Work location identifiers |

---

## Works Filters (`get_rows: "works"`)

### Boolean Filters

| column_id | Description | Example |
|-----------|-------------|---------|
| `open_access.is_oa` | Work is Open Access | `{"column_id": "open_access.is_oa", "value": true}` |
| `is_retracted` | Work has been retracted | `{"column_id": "is_retracted", "value": false}` |
| `is_paratext` | Work is paratext (TOC, cover, etc.) | `{"column_id": "is_paratext", "value": false}` |
| `has_doi` | Work has a DOI | `{"column_id": "has_doi", "value": true}` |
| `has_abstract` | Abstract is available | `{"column_id": "has_abstract", "value": true}` |
| `has_fulltext` | Full text is searchable | `{"column_id": "has_fulltext", "value": true}` |
| `has_orcid` | At least one author has ORCID | `{"column_id": "has_orcid", "value": true}` |
| `has_pmid` | Work is in PubMed | `{"column_id": "has_pmid", "value": true}` |
| `has_pmcid` | Work is in PubMed Central | `{"column_id": "has_pmcid", "value": true}` |
| `has_references` | Work has outgoing citations | `{"column_id": "has_references", "value": true}` |
| `institutions.is_global_south` | Authors from Global South | `{"column_id": "institutions.is_global_south", "value": true}` |
| `primary_location.source.is_oa` | Published in OA source | `{"column_id": "primary_location.source.is_oa", "value": true}` |
| `primary_location.source.is_in_doaj` | Published in DOAJ journal | `{"column_id": "primary_location.source.is_in_doaj", "value": true}` |
| `primary_location.source.is_core` | In CWTS core source | `{"column_id": "primary_location.source.is_core", "value": true}` |
| `open_access.any_repository_has_fulltext` | Free in a repository | `{"column_id": "open_access.any_repository_has_fulltext", "value": true}` |
| `citation_normalized_percentile.is_in_top_1_percent` | Top 1% cited | `{"column_id": "citation_normalized_percentile.is_in_top_1_percent", "value": true}` |
| `citation_normalized_percentile.is_in_top_10_percent` | Top 10% cited | `{"column_id": "citation_normalized_percentile.is_in_top_10_percent", "value": true}` |

### Range Filters

| column_id | Description | Example |
|-----------|-------------|---------|
| `publication_year` | Year published | `{"column_id": "publication_year", "value": 2024, "operator": ">="}` |
| `cited_by_count` | Number of citations | `{"column_id": "cited_by_count", "value": 100, "operator": ">="}` |
| `fwci` | Field-Weighted Citation Impact | `{"column_id": "fwci", "value": 2, "operator": ">="}` |
| `authors_count` | Number of authors | `{"column_id": "authors_count", "value": 5, "operator": "<="}` |
| `countries_distinct_count` | Number of countries | `{"column_id": "countries_distinct_count", "value": 3, "operator": ">="}` |
| `institutions_distinct_count` | Number of institutions | `{"column_id": "institutions_distinct_count", "value": 2, "operator": ">="}` |
| `apc_paid.value_usd` | APC paid in USD | `{"column_id": "apc_paid.value_usd", "value": 5000, "operator": "<="}` |
| `citation_normalized_percentile.value` | Citation percentile (0-100) | `{"column_id": "citation_normalized_percentile.value", "value": 90, "operator": ">="}` |

### Select Entity Filters

| column_id | Entity to Select | Description |
|-----------|-----------------|-------------|
| `type` | types | Work type (article, book, etc.) |
| `authorships.author.id` | authors | Author of the work |
| `authorships.institutions.lineage` | institutions | Author's institution (with hierarchy) |
| `authorships.institutions.id` | institutions | Author's institution (exact) |
| `authorships.countries` | countries | Countries of authors |
| `authorships.institutions.continent` | continents | Continents of institutions |
| `authorships.institutions.type` | institution-types | Type of institutions |
| `primary_location.source.id` | sources | Primary source/journal |
| `primary_location.source.type` | source-types | Type of source |
| `primary_location.source.publisher_lineage` | publishers | Publisher (with hierarchy) |
| `primary_topic.id` | topics | Primary topic |
| `primary_topic.subfield.id` | subfields | Topic subfield |
| `primary_topic.field.id` | fields | Topic field |
| `primary_topic.domain.id` | domains | Topic domain |
| `keywords.id` | keywords | Keywords |
| `concepts.id` | concepts | Concepts (legacy) |
| `sustainable_development_goals.id` | sdgs | UN SDGs |
| `language` | languages | Primary language |
| `best_oa_location.license` | licenses | OA license |
| `open_access.oa_status` | oa-statuses | OA status (gold, green, etc.) |
| `awards.id` | awards | Grant/award ID |
| `awards.funder.id` | funders | Funder of awards |
| `cites` | works | Works this cites |
| `cited_by` | works | Works citing this |
| `related_to` | works | Related works |
| `ids.openalex` | works | OpenAlex ID |
| `corresponding_author_ids` | authors | Corresponding author |
| `corresponding_institution_ids` | institutions | Corresponding institution |

### Search Filters

| column_id | Description | Example |
|-----------|-------------|---------|
| `default.search` | Full text search (title, abstract, body) | `{"column_id": "default.search", "value": "climate change"}` |
| `title_and_abstract.search` | Title and abstract search | `{"column_id": "title_and_abstract.search", "value": "machine learning"}` |
| `display_name.search` | Title only search | `{"column_id": "display_name.search", "value": "neural network"}` |
| `abstract.search` | Abstract only search | `{"column_id": "abstract.search", "value": "methodology"}` |
| `fulltext.search` | Body text only search | `{"column_id": "fulltext.search", "value": "results"}` |
| `raw_affiliation_strings.search` | Raw affiliation string search | `{"column_id": "raw_affiliation_strings.search", "value": "stanford"}` |

---

## Authors Filters (`get_rows: "authors"`)

### Boolean Filters

| column_id | Description |
|-----------|-------------|
| `has_orcid` | Author has ORCID |

### Select Entity Filters

| column_id | Entity to Select | Description |
|-----------|-----------------|-------------|
| `last_known_institutions.id` | institutions | Most recent institution |
| `last_known_institutions.country_code` | countries | Country of last institution |
| `last_known_institutions.type` | institution-types | Type of last institution |
| `affiliations.institution.id` | institutions | Any affiliated institution |

### Search Filters

| column_id | Description |
|-----------|-------------|
| `display_name.search` | Author name search |

---

## Institutions Filters (`get_rows: "institutions"`)

### Select Entity Filters

| column_id | Entity to Select | Description |
|-----------|-----------------|-------------|
| `country_code` | countries | Country |
| `type` | institution-types | Institution type |
| `lineage` | institutions | Parent/child institutions |

### Boolean Filters

| column_id | Description |
|-----------|-------------|
| `is_global_south` | Located in Global South |

---

## Sources Filters (`get_rows: "sources"`)

### Boolean Filters

| column_id | Description |
|-----------|-------------|
| `is_oa` | Open Access source |
| `is_in_doaj` | In DOAJ |

### Select Entity Filters

| column_id | Entity to Select | Description |
|-----------|-----------------|-------------|
| `type` | source-types | Source type (journal, repository) |
| `host_organization_lineage` | publishers | Publisher hierarchy |

---

## Funders Filters (`get_rows: "funders"`)

### Select Entity Filters

| column_id | Entity to Select | Description |
|-----------|-----------------|-------------|
| `country_code` | countries | Country |

### Boolean Filters

| column_id | Description |
|-----------|-------------|
| `is_global_south` | Located in Global South |

---

## Awards Filters (`get_rows: "awards"`)

### Select Entity Filters

| column_id | Entity to Select | Description |
|-----------|-----------------|-------------|
| `funder.id` | funders | Funding organization |

### Range Filters

| column_id | Description |
|-----------|-------------|
| `start_year` | Year award started |

---

## Operators Reference

### Equality Operators

| Operator | URL Syntax | OQL Syntax | Description |
|----------|-----------|------------|-------------|
| `is` | `field:value` | `field is value` | Exact match (default) |
| `is not` | `field:!value` | `field is not value` | Negation |

### Comparison Operators

| Operator | URL Syntax | OQL Syntax | Description |
|----------|-----------|------------|-------------|
| `>=` | `field:value-` | `field ≥ value` | Greater than or equal |
| `<=` | `field:-value` | `field ≤ value` | Less than or equal |
| `>` | N/A | `field > value` | Greater than |
| `<` | N/A | `field < value` | Less than |

### Text Operators

| Operator | Description |
|----------|-------------|
| `contains` | Text search (with stemming) |
| `does not contain` | Negative text search |

---

## URL ↔ OQO ↔ OQL Mapping Examples

| URL | OQO | OQL |
|-----|-----|-----|
| `type:article` | `{"column_id": "type", "value": "types/article"}` | `type is Article [types/article]` |
| `type:!article` | `{"column_id": "type", "value": "types/article", "operator": "is not"}` | `type is not Article [types/article]` |
| `type:article\|book` | `{"join": "or", "filters": [...]}` | `type is Article [types/article] or Book [types/book]` |
| `publication_year:2024-` | `{"column_id": "publication_year", "value": 2024, "operator": ">="}` | `year ≥ 2024` |
| `publication_year:-2020` | `{"column_id": "publication_year", "value": 2020, "operator": "<="}` | `year ≤ 2020` |
| `publication_year:2020-2024` | Two filters with `>=` and `<=` | `year is 2020–2024` |
| `language:null` | `{"column_id": "language", "value": null}` | `language is unknown` |
| `is_oa:true` | `{"column_id": "open_access.is_oa", "value": true}` | `is open access` |
| `authorships.institutions.lineage:i136199984` | `{"column_id": "authorships.institutions.lineage", "value": "institutions/I136199984"}` | `institution is Harvard [institutions/I136199984]` |

---

## Limitations

### URL Format Cannot Express:
- Nested boolean logic like `A AND (B OR C)` where B and C are different fields
- Complex parenthesized expressions across different filter keys

### OQO Supports:
- Full nested boolean logic
- Unlimited nesting depth for branch filters
- Mixed AND/OR at any level

When translating OQO → URL, if the query contains unsupported structures, the URL field will be null with a warning in the validation response.
