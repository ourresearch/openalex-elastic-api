# Query Format Translation Specification

## Overview

This specification defines a system for bidirectional translation between three query formats used in OpenAlex:

1. **URL** — Traditional query parameter syntax (`filter=type:article,year:2024-`)
2. **OQL** — OpenAlex Query Language, human-readable (`Works where type is Article [article] and year ≥ 2024`)
3. **OQO** — OpenAlex Query Object, canonical JSON representation

The goal is to have a single source of truth (OQO) that can be rendered in any format, enabling:
- Copy-pasteable OQL in papers and documentation
- Shareable URLs
- Programmatic JSON access
- Consistent behavior across client and server

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                           CLIENT (Vue)                               │
│                                                                     │
│   ┌─────────────┐    ┌─────────────┐    ┌─────────────┐            │
│   │   Filters   │    │    OQL      │    │    OQO      │            │
│   │  (graphical)│    │   (text)    │    │   (JSON)    │            │
│   └──────┬──────┘    └──────┬──────┘    └──────┬──────┘            │
│          │                  │                  │                    │
│          └──────────────────┼──────────────────┘                    │
│                             ▼                                       │
│                    POST /query/translate                            │
└─────────────────────────────┬───────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│                         SERVER (Python)                              │
│                                                                     │
│   ┌─────────────────────────────────────────────────────────────┐  │
│   │                    /query/translate                          │  │
│   │                                                              │  │
│   │   Input: { entity_type, input_format, input }               │  │
│   │   Output: { url, oql, oqo, validation }                     │  │
│   │                                                              │  │
│   │   ┌──────────┐   ┌──────────┐   ┌──────────┐               │  │
│   │   │ URL      │◄─►│   OQO    │◄─►│   OQL    │               │  │
│   │   │ Parser   │   │ (canon)  │   │ Renderer │               │  │
│   │   └──────────┘   └──────────┘   └──────────┘               │  │
│   │                       │                                      │  │
│   │                       ▼                                      │  │
│   │              ┌──────────────┐                                │  │
│   │              │  Validator   │                                │  │
│   │              │ (fields.py)  │                                │  │
│   │              └──────────────┘                                │  │
│   └─────────────────────────────────────────────────────────────┘  │
│                                                                     │
│   Existing API endpoints also return all 3 formats in meta.query   │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Part 1: OQO (OpenAlex Query Object) Format

OQO is the canonical JSON representation. All translations go through OQO.

### 1.1 Top-Level Structure

```json
{
  "get_rows": "works",              // Required: entity type
  "filter_rows": [...],             // Filters applied to rows being retrieved
  "sort_by_column": "cited_by_count",
  "sort_by_order": "desc",
  "sample": 100                     // Optional
}
```

### 1.2 Filter Structure

#### Leaf Filter (single condition)
```json
{
  "column_id": "publication_year",   // Required: the filter field
  "value": "2024",                   // Required: the filter value
  "operator": "is"                   // Optional: defaults to "is"
}
```

#### Branch Filter (boolean combination)
```json
{
  "join": "or",                      // Required: "and" or "or"
  "filters": [                       // Required: array of leaf or branch filters
    {"column_id": "type", "value": "article"},
    {"column_id": "type", "value": "book"}
  ]
}
```

### 1.3 Operators

| Operator | Use Case | Example |
|----------|----------|---------|
| `is` | Exact match (default) | `{"column_id": "type", "value": "article"}` |
| `is not` | Negation | `{"column_id": "type", "value": "article", "operator": "is not"}` |
| `>` | Greater than | `{"column_id": "publication_year", "value": "2020", "operator": ">"}` |
| `<` | Less than | `{"column_id": "cited_by_count", "value": "100", "operator": "<"}` |
| `>=` | Range inclusive | `{"column_id": "fwci", "value": "2", "operator": ">="}` |
| `<=` | Range inclusive | `{"column_id": "publication_year", "value": "2024", "operator": "<="}` |
| `contains` | Text search | `{"column_id": "title.search", "value": "climate", "operator": "contains"}` |

### 1.4 Examples

#### Simple filter
```json
{
  "get_rows": "works",
  "filter_rows": [
    {"column_id": "type", "value": "types/article"}
  ]
}
```

#### Multiple filters (AND at top level)
```json
{
  "get_rows": "works",
  "filter_rows": [
    {"column_id": "type", "value": "types/article"},
    {"column_id": "publication_year", "value": "2024", "operator": ">="},
    {"column_id": "open_access.is_oa", "value": true}
  ]
}
```

#### OR within same field (type is article OR book)
```json
{
  "get_rows": "works",
  "filter_rows": [
    {
      "join": "or",
      "filters": [
        {"column_id": "type", "value": "types/article"},
        {"column_id": "type", "value": "types/book"}
      ]
    }
  ]
}
```

#### AND within same field (co-authorship: institution A AND institution B)
```json
{
  "get_rows": "works",
  "filter_rows": [
    {"column_id": "authorships.institutions.lineage", "value": "institutions/I33213144"},
    {"column_id": "authorships.institutions.lineage", "value": "institutions/I103163165"}
  ]
}
```

#### Nested boolean (Harvard AND (Stanford OR MIT))
```json
{
  "get_rows": "works",
  "filter_rows": [
    {"column_id": "authorships.institutions.lineage", "value": "institutions/I136199984"},
    {
      "join": "or",
      "filters": [
        {"column_id": "authorships.institutions.lineage", "value": "institutions/I97018004"},
        {"column_id": "authorships.institutions.lineage", "value": "institutions/I63966007"}
      ]
    }
  ]
}
```

#### Negation (type is NOT article)
```json
{
  "get_rows": "works",
  "filter_rows": [
    {"column_id": "type", "value": "types/article", "operator": "is not"}
  ]
}
```

---

## Part 2: URL Format

The traditional query parameter syntax used in shareable URLs.

### 2.1 Basic Syntax

```
/works?filter=field1:value1,field2:value2&sort=field:order
```

### 2.2 Operators in URL

| URL Syntax | Meaning | OQO Equivalent |
|------------|---------|----------------|
| `field:value` | Equals | `operator: "is"` |
| `field:!value` | Not equals | `operator: "is not"` |
| `field:value1\|value2` | OR | `join: "or"` branch |
| `field:value1,field:value2` | AND (same field) | Two separate filters |
| `field:2020-` | Greater than or equal | `operator: ">="` |
| `field:-2024` | Less than or equal | `operator: "<="` |
| `field:2020-2024` | Range | Two filters with `>=` and `<=` |
| `field:null` | Is unknown | `value: null` |
| `field:!null` | Is not unknown | `value: null, operator: "is not"` |

### 2.3 Limitations

URL format **cannot express**:
- Nested boolean logic like `A AND (B OR C)` where B and C are different fields
- Complex parenthesized expressions

When translating OQO → URL, if the query contains unsupported structures, return an error in the `validation` field.

---

## Part 3: OQL Format

Human-readable query language for copy-paste and display.

### 3.1 Basic Syntax

```
{EntityType} where {clause} [and {clause}]* [; sort by {field}] [; sample {n}]
```

### 3.2 Clause Types

#### Boolean
```
is open access                    → open_access.is_oa:true
is not retracted                  → is_retracted:false
has a DOI                         → has_doi:true
```

#### Range
```
year ≥ 2024                       → publication_year:2024-
year ≤ 2020                       → publication_year:-2020
year is 2020–2024                 → publication_year:2020-2024
citations = 100                   → cited_by_count:100
```

#### Select Entity (with bracketed IDs)
```
type is Article [article]         → type:article
institution is MIT [i63966007]    → authorships.institutions.lineage:i63966007
country is Germany [de]           → authorships.countries:de
SDG is Climate Action [13]        → sustainable_development_goals.id:13
```

#### Search
```
title includes "machine learning" → display_name.search:machine learning
title & abstract includes "climate" → title_and_abstract.search:climate
```

#### Multiple Values (OR)
```
type is Article [article] or Book [book]
```

#### Multiple Values (AND with same field)
```
institution is University of Florida [i33213144] and Florida State University [i103163165]
```

#### Negation
```
type is not Article [article]
type is not Article [article] and not Book [book]
```

### 3.3 Display Name Resolution

When rendering OQO → OQL, the server must resolve entity IDs to display names:
- `i63966007` → "MIT"
- `article` → "Article"
- `de` → "Germany"

This requires API lookups or cached entity metadata.

### 3.4 Native vs Non-Native Entities

**Native entities** (OpenAlex-minted IDs) require bracketed IDs in OQL:
- institutions: `[i123456]`
- authors: `[a123456]`
- works: `[w123456]`
- sources: `[s123456]`
- topics: `[t123456]`
- funders: `[f123456]`
- publishers: `[p123456]`

**Non-native entities** also use bracketed IDs for consistency:
- types: `[article]`, `[book-chapter]`
- countries: `[de]`, `[us]`
- SDGs: `[3]`, `[13]`
- OA statuses: `[gold]`, `[green]`

---

## Part 4: API Endpoint

### 4.1 POST /query/translate

Translates between query formats.

#### Request
```json
{
  "entity_type": "works",                    // Required
  "input_format": "url" | "oql" | "oqo",     // Required
  "input": "..."                             // Required: the query in input_format
}
```

#### Response (Success)
```json
{
  "url": {
    "filter": "type:article,publication_year:2024-",
    "sort": "cited_by_count:desc",
    "sample": null
  },
  "oql": "Works where type is Article [article] and year ≥ 2024; sort by citation count",
  "oqo": {
    "get_rows": "works",
    "filter_rows": [
      {"column_id": "type", "value": "types/article"},
      {"column_id": "publication_year", "value": "2024", "operator": ">="}
    ],
    "sort_by_column": "cited_by_count",
    "sort_by_order": "desc"
  },
  "validation": {
    "valid": true,
    "warnings": []
  }
}
```

#### Response (Error)
```json
{
  "url": null,
  "oql": null,
  "oqo": null,
  "validation": {
    "valid": false,
    "errors": [
      {
        "type": "invalid_field",
        "message": "fake_field is not a valid filter field",
        "location": "filter_rows[0].column_id"
      }
    ]
  }
}
```

#### Response (Partial - nested boolean can't convert to URL)
```json
{
  "url": null,
  "oql": "Works where institution is Harvard [institutions/I136199984] and (Stanford [institutions/I97018004] or MIT [institutions/I63966007])",
  "oqo": { ... },
  "validation": {
    "valid": true,
    "warnings": [
      {
        "type": "url_not_expressible",
        "message": "Nested boolean logic cannot be expressed in URL format"
      }
    ]
  }
}
```

### 4.2 Enhanced API Responses

All existing entity endpoints (`/works`, `/authors`, etc.) should include query formats in the meta section:

```json
{
  "meta": {
    "count": 12345,
    "page": 1,
    "per_page": 25,
    "query": {
      "url": {
        "filter": "type:article",
        "sort": "cited_by_count:desc"
      },
      "oql": "Works where type is Article [article]; sort by citation count",
      "oqo": {
        "get_rows": "works",
        "filter_rows": [{"column_id": "type", "value": "types/article"}],
        "sort_by_column": "cited_by_count",
        "sort_by_order": "desc"
      }
    }
  },
  "results": [...]
}
```

---

## Part 5: Server Implementation

### 5.1 File Structure

```
openalex-elastic-api/
├── query_translation/
│   ├── __init__.py
│   ├── views.py              # Flask blueprint for /query/translate
│   ├── oqo.py                # OQO data model (Pydantic or dataclass)
│   ├── url_parser.py         # URL filter string → OQO
│   ├── url_renderer.py       # OQO → URL filter string
│   ├── oql_parser.py         # OQL string → OQO (port PEG grammar)
│   ├── oql_renderer.py       # OQO → OQL string
│   ├── display_names.py      # Entity ID → display name resolution
│   └── validator.py          # Validate OQO against field definitions
├── tests/
│   └── test_query_translation.py
```

### 5.2 Key Components

#### OQO Data Model (`oqo.py`)
```python
from dataclasses import dataclass
from typing import List, Optional, Union, Literal

@dataclass
class LeafFilter:
    column_id: str
    value: Union[str, int, bool, None]
    operator: str = "is"

@dataclass
class BranchFilter:
    join: Literal["and", "or"]
    filters: List[Union["LeafFilter", "BranchFilter"]]

@dataclass
class OQO:
    get_rows: str
    filter_rows: List[Union[LeafFilter, BranchFilter]]
    sort_by_column: Optional[str] = None
    sort_by_order: Optional[Literal["asc", "desc"]] = None
    sample: Optional[int] = None
```

#### URL Parser (`url_parser.py`)
- Parse `filter=field1:value1,field2:value2` into OQO
- Handle `|` (OR), `!` (NOT), ranges (`-`), `null`
- Multiple instances of same field become separate filters (AND)

#### OQL Parser (`oql_parser.py`)
- Port the PEG grammar from `openalex-gui/src/oql.pegjs`
- Use `parsimonious` or `pyparsing` Python library
- Parse into OQO structure

#### Display Name Resolver (`display_names.py`)
- Cache entity display names
- Batch lookups for efficiency
- Fallback to ID-only if lookup fails

### 5.3 Filter Field Definitions (Source of Truth)

Valid filter fields are defined in `{entity}/fields.py`:
- `works/fields.py` → `fields` list
- `authors/fields.py` → `fields` list
- etc.

The `param` attribute of each field is the canonical filter key.

**Important**: These must stay in sync with `facetConfigs.js` on the client. For now, this is manual; a syncing system can be built later.

---

## Part 6: Client Implementation

### 6.1 UI Changes

Replace the current toggle (`[Filters | OQL]`) with a dropdown:

```
┌─────────────────────────────────────────┐
│ Query Format: [Filters ▼]               │
├─────────────────────────────────────────┤
│   ○ Filters                             │
│   ○ OQL                                 │
│   ○ OQO                                 │
└─────────────────────────────────────────┘
```

### 6.2 Mode Behavior

| Mode | Display | Edit | Validation |
|------|---------|------|------------|
| **Filters** | Graphical filter chips | Inline modification | Client-side (existing) |
| **OQL** | Formatted text with clickable entities | "Edit" → textarea | Server-side only |
| **OQO** | Formatted JSON | "Edit" → code textarea | Server-side only |

### 6.3 Edit Flow (OQL/OQO modes)

1. User clicks "Edit" button
2. Content becomes editable textarea
3. User modifies the query
4. User clicks "Apply"
5. Client sends `POST /query/translate` with the edited content
6. Server validates and returns all three formats
7. **If valid**: 
   - Update URL with new filter params
   - Refresh results
   - Exit edit mode
8. **If error**:
   - Display error message inline
   - Keep edit mode open
   - User can fix and retry

### 6.4 No Client-Side Validation

For OQL and OQO modes, **all validation happens on the server**. The client simply:
1. Sends the raw text/JSON to the server
2. Displays the server's response (success or error)

This keeps the client simple and ensures consistency.

### 6.5 Component Structure

```
src/components/Filter/
├── QueryFormatSelector.vue      # New: dropdown + mode switching
├── OqlDisplay.vue               # Existing: enhance with edit mode
├── OqoDisplay.vue               # New: JSON display + edit mode
├── FilterTray.vue               # Existing: graphical filters
```

---

## Part 7: Test Cases

### 7.1 Round-Trip Tests (URL → OQO → URL)

```python
ROUND_TRIP_TESTS = [
    # Boolean filters
    ("works", "is_oa:true", None),
    ("works", "is_retracted:false", None),
    ("works", "has_doi:true", None),
    
    # Range filters
    ("works", "publication_year:2024", None),
    ("works", "publication_year:2020-2024", None),
    ("works", "publication_year:2020-", None),
    ("works", "cited_by_count:-100", None),
    ("works", "fwci:2-", None),
    
    # Select single value
    ("works", "type:article", None),
    ("works", "authorships.institutions.lineage:i33213144", None),
    ("works", "authorships.countries:us", None),
    
    # Select OR (pipe)
    ("works", "type:article|review", None),
    ("works", "authorships.institutions.lineage:i33213144|i63966007", None),
    
    # Select AND (same field, comma-separated)
    ("works", "authorships.institutions.lineage:i33213144,authorships.institutions.lineage:i103163165", None),
    ("works", "authorships.author.id:a123,authorships.author.id:a456", None),
    
    # Negation
    ("works", "type:!article", None),
    ("works", "type:!article|review", None),
    
    # Search
    ("works", "title.search:machine learning", None),
    ("works", "title_and_abstract.search:climate change", None),
    
    # Multiple different filters
    ("works", "type:article,publication_year:2024-,is_oa:true", None),
    
    # With sort
    ("works", "type:article", "cited_by_count:desc"),
    
    # Null values
    ("works", "language:null", None),
    ("works", "language:!null", None),
    
    # Other entities
    ("authors", "last_known_institutions.id:i33213144", None),
    ("institutions", "type:education", None),
]
```

### 7.2 OQL Parsing Tests

```python
OQL_PARSING_TESTS = [
    # Basic entity with bracketed ID
    ("works where institution is University of Cambridge [i241749]",
     {"entity": "works", "filters": [{"column_id": "authorships.institutions.lineage", "value": "i241749"}]}),
    
    # ID-only (no display name)
    ("works where institution is [i241749]",
     {"entity": "works", "filters": [{"column_id": "authorships.institutions.lineage", "value": "i241749"}]}),
    
    # Non-native entity
    ("works where type is Article [article]",
     {"entity": "works", "filters": [{"column_id": "type", "value": "article"}]}),
    
    # Hyphenated ID
    ("works where type is Book Chapter [book-chapter]",
     {"entity": "works", "filters": [{"column_id": "type", "value": "book-chapter"}]}),
    
    # Country
    ("works where country is Germany [de]",
     {"entity": "works", "filters": [{"column_id": "authorships.countries", "value": "de"}]}),
    
    # SDG with numeric ID
    ("works where sustainable development goal is Climate Action [13]",
     {"entity": "works", "filters": [{"column_id": "sustainable_development_goals.id", "value": "13"}]}),
    
    # Range filters
    ("works where year ≥ 2024",
     {"entity": "works", "filters": [{"column_id": "publication_year", "value": "2024", "operator": ">="}]}),
    
    ("works where citations is 100–500",
     {"entity": "works", "filters": [
         {"column_id": "cited_by_count", "value": "100", "operator": ">="},
         {"column_id": "cited_by_count", "value": "500", "operator": "<="}
     ]}),
    
    # Boolean
    ("works where is open access",
     {"entity": "works", "filters": [{"column_id": "open_access.is_oa", "value": True}]}),
    
    # Search
    ('works where title includes "machine learning"',
     {"entity": "works", "filters": [{"column_id": "display_name.search", "value": "machine learning"}]}),
    
    # Multiple values OR
    ("works where type is Article [article] or Book [book]",
     {"entity": "works", "filters": [{"join": "or", "filters": [
         {"column_id": "type", "value": "article"},
         {"column_id": "type", "value": "book"}
     ]}]}),
    
    # Multiple values AND (same field)
    ("works where institution is University of Florida [i33213144] and Florida State University [i103163165]",
     {"entity": "works", "filters": [
         {"column_id": "authorships.institutions.lineage", "value": "i33213144"},
         {"column_id": "authorships.institutions.lineage", "value": "i103163165"}
     ]}),
    
    # Negation
    ("works where type is not Article [article]",
     {"entity": "works", "filters": [{"column_id": "type", "value": "article", "operator": "is not"}]}),
    
    # Mixed positive and negated
    ("works where type is Article [article] and not Book [book]",
     {"entity": "works", "filters": [
         {"column_id": "type", "value": "article"},
         {"column_id": "type", "value": "book", "operator": "is not"}
     ]}),
    
    # Parentheses
    ("works where institution is Harvard [i136199984] and (Stanford [i97018004] or MIT [i63966007])",
     {"entity": "works", "filters": [
         {"column_id": "authorships.institutions.lineage", "value": "i136199984"},
         {"join": "or", "filters": [
             {"column_id": "authorships.institutions.lineage", "value": "i97018004"},
             {"column_id": "authorships.institutions.lineage", "value": "i63966007"}
         ]}
     ]}),
    
    # Sort
    ("works where type is Article [article]; sort by citation count",
     {"entity": "works", "filters": [...], "sort_by_column": "cited_by_count", "sort_by_order": "desc"}),
    
    # Sample
    ("works where year ≥ 2024; sample 100",
     {"entity": "works", "filters": [...], "sample": 100}),
]
```

### 7.3 Three-Way Equivalence Tests

```python
EQUIVALENCE_TESTS = [
    {
        "description": "Simple type filter",
        "url": {"filter": "type:article"},
        "oql": "Works where type is Article [article]",
        "oqo": {
            "get_rows": "works",
            "filter_rows": [{"column_id": "type", "value": "types/article"}]
        }
    },
    {
        "description": "Year range with sort",
        "url": {"filter": "publication_year:2024-", "sort": "fwci:desc"},
        "oql": "Works where year ≥ 2024; sort by FWCI",
        "oqo": {
            "get_rows": "works",
            "filter_rows": [{"column_id": "publication_year", "value": "2024", "operator": ">="}],
            "sort_by_column": "fwci",
            "sort_by_order": "desc"
        }
    },
    {
        "description": "Co-authorship (AND same field)",
        "url": {"filter": "authorships.institutions.lineage:i33213144,authorships.institutions.lineage:i103163165"},
        "oql": "Works where institution is University of Florida [i33213144] and Florida State University [i103163165]",
        "oqo": {
            "get_rows": "works",
            "filter_rows": [
                {"column_id": "authorships.institutions.lineage", "value": "institutions/I33213144"},
                {"column_id": "authorships.institutions.lineage", "value": "institutions/I103163165"}
            ]
        }
    },
    {
        "description": "OR within same field",
        "url": {"filter": "type:article|book"},
        "oql": "Works where type is Article [article] or Book [book]",
        "oqo": {
            "get_rows": "works",
            "filter_rows": [{
                "join": "or",
                "filters": [
                    {"column_id": "type", "value": "types/article"},
                    {"column_id": "type", "value": "types/book"}
                ]
            }]
        }
    },
    {
        "description": "OA compliance query",
        "url": {"filter": "authorships.institutions.lineage:i241749,open_access.oa_status:gold,type:article"},
        "oql": "Works where institution is University of Cambridge [i241749] and Open Access status is gold [gold] and type is Article [article]",
        "oqo": {
            "get_rows": "works",
            "filter_rows": [
                {"column_id": "authorships.institutions.lineage", "value": "institutions/I241749"},
                {"column_id": "open_access.oa_status", "value": "oa-statuses/gold"},
                {"column_id": "type", "value": "types/article"}
            ]
        }
    },
]
```

### 7.4 Error Cases

```python
ERROR_TESTS = [
    # Invalid field
    ("url", "fake_field:value", "fake_field is not a valid filter field"),
    
    # Missing value
    ("url", "type:", "Missing value for filter"),
    
    # Invalid entity type
    ("oql", "Widgets where type is foo", "Widgets is not a valid entity"),
    
    # Native entity without bracketed ID
    ("oql", "works where institution is Harvard", "Native entity values require bracketed IDs"),
    
    # Invalid operator
    ("oqo", {"filter_rows": [{"column_id": "type", "value": "types/article", "operator": "equals"}]}, 
     "equals is not a valid operator"),
    
    # Nested boolean → URL (warning, not error)
    ("oqo", {"filter_rows": [{"column_id": "x", "value": "1"}, {"join": "or", "filters": [...]}]},
     "warning: Nested boolean not expressible in URL format"),
]
```

---

## Part 8: Implementation Phases

### Phase 1: Core Translation (MVP)

1. **Server**: Implement `/query/translate` endpoint
   - OQO data model
   - URL ↔ OQO conversion
   - Basic validation against `fields.py`
   
2. **Server**: Add `meta.query` to existing API responses

3. **Client**: Add OQO display mode (read-only)

**Deliverables**:
- URL ↔ OQO round-trip works
- API responses include all 3 formats
- Users can view OQO in UI

### Phase 2: OQL Support

1. **Server**: Port OQL parser from JavaScript
2. **Server**: Implement OQL renderer (OQO → OQL)
3. **Server**: Display name resolution
4. **Client**: Add OQL edit mode with server validation

**Deliverables**:
- Full OQL ↔ OQO conversion
- Users can edit OQL in UI

### Phase 3: Polish & Edge Cases

1. Handle all edge cases (null, negation, ranges)
2. Comprehensive test coverage
3. Performance optimization (caching display names)
4. Error message improvements

---

## Part 9: Open Questions

1. **Nested boolean in Elasticsearch**: Currently not supported. When we add support, the OQO → Elasticsearch converter needs updating, but OQO format itself is ready.

2. **filter_aggs**: Currently out of scope. The OQO format supports it, but translation focuses on `filter_works` for now.

3. **Config syncing**: For now, `{entity}/fields.py` (server) and `facetConfigs.js` (client) are manually kept in sync. A future system could auto-generate one from the other.

4. **Display name caching**: How aggressively to cache? Redis? In-memory? Per-request?

---

## References

- **OQL Spec (client)**: `/openalex-gui/docs/oql-spec.md`
- **OQL Grammar (client)**: `/openalex-gui/src/oql.pegjs`
- **OQL Tests (client)**: `/openalex-gui/src/__tests__/oql.test.js`
- **OQO Validator (server)**: `/openalex-elastic-api/oql/validate.py`
- **Works Fields (server)**: `/openalex-elastic-api/works/fields.py`
