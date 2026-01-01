# OQL (OpenAlex Query Language) Specification v1.1

## Overview

OQL is a human-readable query language that bidirectionally converts to/from OQO (OpenAlex Query Object) and URL parameters. It's designed to be:

- **Copy-pasteable** — Users can include OQL in papers/slides, and others can paste it into OpenAlex to reproduce results
- **Unambiguous** — Entity IDs are always enclosed in brackets `[id]`
- **Deterministic** — No AI required; purely rule-based conversion

### Design Philosophy

- **Strict output**: Always emit the most human-readable OQL with display names
- **Permissive input**: Accept both technical names and display names when parsing

### Relationship to Other Formats

OQL is one of three interchangeable query formats:

```
URL ←→ OQO ←→ OQL
```

- **OQO** (OpenAlex Query Object): The canonical JSON format. All translations go through OQO.
- **URL**: Traditional query parameters (`filter=type:article,publication_year:2024-`)
- **OQL**: Human-readable text (`Works where it's Open Access and year >= 2024`)

See `query-format-translation-spec.md` for the complete translation system.
See `oqo-schema.json` for the OQO JSON schema.

---

## 1. Syntax Structure

### 1.1 Basic Format

```
{EntityType} where {clause} [and {clause}]* [; sort by {field} {order}] [; sample {n}]
```

### 1.2 Entity Type (Required)

Statement **must** begin with a capitalized entity type:

- `Works where ...`
- `Authors where ...`
- `Sources where ...`
- `Institutions where ...`
- `Funders where ...`
- `Publishers where ...`
- `Topics where ...`
- `Keywords where ...`
- `Concepts where ...`
- `Awards where ...`
- `Countries where ...`
- `Continents where ...`
- `Sdgs where ...`
- `Languages where ...`
- `Licenses where ...`
- `Types where ...`
- `Source Types where ...`
- `Institution Types where ...`

### 1.3 Conjunctions

- **AND**: Top-level clauses are joined by `and`
- **OR**: Expressed within branch filters using parentheses

---

## 2. Technical vs Human-Readable Formats

OQL supports **two equivalent syntaxes**. Both are valid for input, but the **human-readable format is preferred for output**.

### 2.1 Technical Format (Valid Input)

Uses column_id keys and raw value IDs:

```
Works where open_access.is_oa is true and sustainable_development_goals.id is [sdgs/2] and authorships.countries is [countries/ca] and institutions.is_global_south is true and publication_year >= 2020
```

### 2.2 Human-Readable Format (Preferred Output)

Uses display names for columns and includes display names before bracketed IDs:

```
Works where it's Open Access and Sustainable Development Goals is Zero Hunger [2] and Country is Canada [ca] and it's from Global South and year >= 2020
```

### 2.3 Key Differences

| Aspect | Technical | Human-Readable |
|--------|-----------|----------------|
| Column names | `open_access.is_oa` | `Open Access` (display name) |
| Boolean filters | `open_access.is_oa is true` | `it's Open Access` |
| Entity values | `[sdgs/2]` | `Zero Hunger [2]` |

---

## 3. Filter Types & Syntax

### 3.1 Boolean Filters

Boolean filters have a special human-readable syntax using `it's`:

| Technical | Human-Readable |
|-----------|----------------|
| `open_access.is_oa is true` | `it's Open Access` |
| `open_access.is_oa is false` | `it's not Open Access` |
| `institutions.is_global_south is true` | `it's from Global South` |
| `institutions.is_global_south is false` | `it's not from Global South` |
| `is_retracted is true` | `it's retracted` |
| `has_doi is true` | `it has a DOI` |
| `has_doi is false` | `it doesn't have a DOI` |

The display name comes from the column's `displayName` in the config.

### 3.2 Select Entity Filters

For filters that select entities, the format includes an optional display name before the bracketed ID:

**Technical** (namespaced ID in brackets - accepted for backward compatibility):
```
sustainable_development_goals.id is [sdgs/2]
authorships.countries is [countries/ca]
authorships.institutions.lineage is [institutions/I136199984]
```

**Human-Readable** (display name + short ID in brackets - preferred output):
```
Sustainable Development Goals is Zero Hunger [2]
Country is Canada [ca]
institution is Harvard University [I136199984]
```

**IMPORTANT**: The bracketed ID is **always required** and is the source of truth. The display name before it is optional for input but preferred for output.

### 3.3 Comparison Filters (>=, <=, >, <)

For numeric and date fields. Display names can be used for the column:

**Technical**:
```
publication_year >= 2020
cited_by_count <= 100
fwci > 2
```

**Human-Readable**:
```
year >= 2020
citations <= 100
FWCI > 2
```

### 3.4 Text Search Filters (contains / does not contain)

**Technical**:
```
title_and_abstract.search contains "machine learning"
display_name.search contains "climate"
```

**Human-Readable**:
```
title & abstract contains "machine learning"
title contains "climate"
```

### 3.5 Null Values

```
language is unknown           → filter for unknown/missing values
language is not unknown       → filter for known values
```

Or technical:
```
language is null
language is not null
```

---

## 4. Bracketed IDs

**All entity IDs must be enclosed in brackets `[id]`**. This is a critical requirement for unambiguous parsing.

### 4.1 Format

Preferred output format (short ID):
```
[{short_id}]
```

Backward-compatible input format (namespaced ID):
```
[{entity_type}/{short_id}]
```

### 4.2 Examples

| Entity Type | Preferred Output | Also Accepted (Input) |
|-------------|------------------|----------------------|
| institutions | `[I136199984]` | `[institutions/I136199984]` |
| authors | `[A5023888391]` | `[authors/A5023888391]` |
| works | `[W2741809807]` | `[works/W2741809807]` |
| sources | `[S137773608]` | `[sources/S137773608]` |
| topics | `[T10012]` | `[topics/T10012]` |
| funders | `[F4320332161]` | `[funders/F4320332161]` |
| publishers | `[P4310319908]` | `[publishers/P4310319908]` |
| types | `[article]` | `[types/article]` |
| countries | `[ca]` | `[countries/ca]` |
| sdgs | `[2]` | `[sdgs/2]` |
| oa-statuses | `[gold]` | `[oa-statuses/gold]` |
| languages | `[en]` | `[languages/en]` |

### 4.3 With Display Names (Preferred Output)

When outputting OQL, include the display name before the bracketed short ID:

```
Harvard University [I136199984]
Zero Hunger [2]
Canada [ca]
article [article]
```

---

## 5. Boolean Logic

### 5.1 Top-Level AND

Multiple filters at the top level are implicitly AND-ed:

```
Works where it's Open Access and year >= 2024 and Country is Canada [countries/ca]
```

### 5.2 OR with Parentheses

OR requires parentheses:

```
Works where (type is article [article] or type is book [book])
```

### 5.3 Nested Boolean

Complex boolean expressions are supported:

```
Works where institution is Harvard University [I136199984] and (institution is Stanford University [I97018004] or institution is MIT [I63966007])
```

**Note**: Nested boolean cannot always be expressed in URL format.

---

## 6. Sort and Sample

### 6.1 Sort (Optional)

```
; sort by {column} {order}
```

Display names can be used:
```
Works where it's Open Access; sort by citations desc
Works where year >= 2024; sort by FWCI desc
```

### 6.2 Sample (Optional)

```
; sample {n}
```

---

## 7. Column Display Name Mapping

The following mappings are used to convert between technical column_ids and display names:

| column_id | displayName |
|-----------|-------------|
| `publication_year` | year |
| `cited_by_count` | citations |
| `fwci` | FWCI |
| `type` | type |
| `open_access.is_oa` | Open Access |
| `authorships.institutions.lineage` | institution |
| `authorships.author.id` | author |
| `authorships.countries` | Country |
| `primary_location.source.id` | source |
| `primary_topic.id` | topic |
| `grants.funder` | funder |
| `sustainable_development_goals.id` | Sustainable Development Goals |
| `title_and_abstract.search` | title & abstract |
| `display_name.search` | title |
| `language` | language |
| `is_retracted` | retracted |
| `has_doi` | has a DOI |
| `institutions.is_global_south` | from Global South |

---

## 8. Complete Examples

### Example 1: Human-Readable (Preferred Output)

**OQL**:
```
Works where it's Open Access and Sustainable Development Goals is Zero Hunger [2] and Country is Canada [ca] and it's from Global South and year >= 2020
```

**OQO**:
```json
{
  "get_rows": "works",
  "filter_rows": [
    {"column_id": "open_access.is_oa", "value": true},
    {"column_id": "sustainable_development_goals.id", "value": "sdgs/2"},
    {"column_id": "authorships.countries", "value": "countries/ca"},
    {"column_id": "institutions.is_global_south", "value": true},
    {"column_id": "publication_year", "value": 2020, "operator": ">="}
  ]
}
```

### Example 2: Technical (Also Valid Input)

**OQL**:
```
Works where open_access.is_oa is true and sustainable_development_goals.id is [sdgs/2] and authorships.countries is [countries/ca] and institutions.is_global_south is true and publication_year >= 2020
```

Same OQO as above.

### Example 3: OR Filter with Display Names

**OQL**:
```
Works where (type is article [article] or type is book [book])
```

**OQO**:
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

### Example 4: Search with Sample

**OQL**:
```
Works where title & abstract contains "machine learning" and year >= 2020; sample 100
```

**OQO**:
```json
{
  "get_rows": "works",
  "filter_rows": [
    {"column_id": "title_and_abstract.search", "value": "machine learning", "operator": "contains"},
    {"column_id": "publication_year", "value": 2020, "operator": ">="}
  ],
  "sample": 100
}
```

### Example 5: Negation

**OQL**:
```
Works where type is not article [article]
```

Or human-readable for boolean:
```
Works where it's not Open Access
```

---

## 9. Valid Operators

| Operator | OQL Syntax | Use Case |
|----------|------------|----------|
| `is` | `column is value` | Exact match (default) |
| `is not` | `column is not value` | Negation |
| `>=` | `column >= value` | Greater than or equal |
| `<=` | `column <= value` | Less than or equal |
| `>` | `column > value` | Greater than |
| `<` | `column < value` | Less than |
| `contains` | `column contains value` | Text search |
| `does not contain` | `column does not contain value` | Negative text search |

---

## 10. Parsing Rules

### 10.1 Input Parsing Priority

1. Check for boolean pattern: `it's [not] {displayName}`
2. Check for bracketed ID: extract `[entity_type/id]`
3. Check for display name before brackets: `{display_name} [{id}]`
4. Match column name (display name or column_id)
5. Parse operator and value

### 10.2 Display Name Before Bracket is Optional

When parsing, if a display name appears before a bracketed ID, it is validated but the **bracketed ID is the source of truth**.

Valid inputs:
```
Country is Canada [ca]              ✓ (display name + short ID - preferred)
Country is [ca]                     ✓ (short ID only)
Country is Canada [countries/ca]    ✓ (namespaced ID - backward compatible)
Country is [countries/ca]           ✓ (namespaced ID only - backward compatible)
Country is Canada                   ✗ (no ID - error)
```

### 10.3 Display Name Validation

If a display name is provided, it should match the entity's actual display name. Mismatches produce a warning but the query still works (ID is authoritative).

---

## 11. Implementation

### Files

- `oql_renderer.py` — OQO → OQL (outputs human-readable format)
- `oql_parser.py` — OQL → OQO (accepts both formats)

### Display Name Resolution

The renderer requires access to:
1. Column config (column_id → displayName mapping)
2. Entity display names (entity ID → display_name)

Entity display names are fetched from the API or cached.

---

## 12. Related Documentation

- `query-format-translation-spec.md` — Complete translation system (URL ↔ OQO ↔ OQL)
- `oqo-schema.json` — JSON Schema for OQO format
- `oqo-column-reference.md` — Complete list of valid column_ids by entity type
