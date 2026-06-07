# OQO (OpenAlex Query Object) Specification

**Human-readable wrapper for `docs/oqo-schema.json`.** The schema is the
machine-readable contract and is **generated** from the canonical dataclass
(`query_translation/oqo.py`) by `query_translation/regen_schema.py` — never
hand-edited. This document explains the model, the design decisions behind it,
and the equality / canonicalization / rendering / serialization stances so future
work doesn't relitigate them.

Scope: **Stage A (filter / sort / sample) + Stage B (group_by)**. Stage C
(filtering on groups / HAVING) and embedding-as-query are out of scope.

> Provenance: this spec and schema are the deliverable of oxjob **#284**. The
> worked-examples corpus that pressure-tested it (43 real queries spanning WoS /
> Scopus / Dimensions / OXURL / OQO, each OXURL verified live) lives in that job.

---

## 1. The object

An OQO is one JSON object:

```jsonc
{
  "get_rows": "works",              // entity type to return (required)
  "filter_rows": [ <Filter>, ... ], // implicitly AND-joined at the top level
  "group_by":   [ <GroupBy>, ... ], // Stage B grouping dimensions (a list)
  "sort_by":    [ <SortBy>, ... ],  // ordered sort keys (primary, secondary, …)
  "sample": 100                     // random sample of N, or null
}
```

A **`Filter`** is either a **`LeafFilter`** (one condition) or a **`BranchFilter`**
(a boolean combination):

```jsonc
// LeafFilter — a single proposition (a "literal" = atom + polarity)
{ "column_id": "publication_year", "value": 2020, "operator": ">=", "is_negated": false }

// BranchFilter — AND/OR of child filters
{ "join": "or", "filters": [ <Filter>, <Filter>, ... ], "is_negated": false }
```

A **`GroupBy`** is `{ "column_id": "primary_topic.id" }`.

A **`SortBy`** is one sort key: `{ "column_id": "cited_by_count", "direction": "desc" }`
(`direction` is `"asc"` | `"desc"`, default `"asc"`). `sort_by` is an **ordered list**
of these, so a multi-column sort — e.g. `sort=publication_year:desc,cited_by_count:desc`
on the URL surface — is expressible; the list order is the tiebreaker priority and is
**preserved** (never sorted), unlike the commutative top-level `filter_rows`. `column_id`
may be a real sortable column or a synthetic key: `relevance_score` (requires a search
clause; descending only) or, when a `group_by` is present, the bucket-ordering keys
`count` / `key`. Absent/empty ⇒ the entity's implicit default sort.

`get_rows` ∈ the entity enum (works, authors, institutions, sources, publishers,
funders, topics, …). The full enum is in the schema (sourced from
`VALID_ENTITY_TYPES`).

---

## 2. Values are **bare** (the column is the namespace)

A filter `value` is a **bare scalar**. The namespace/type is carried by
`column_id`, resolved via the **column registry** (§7) — it is *not* re-encoded as
a prefix on the value.

| Reference | OQO value | Not |
|---|---|---|
| Harvard | `"I136199984"` | ~~`"institutions/I136199984"`~~ |
| Germany | `"de"` | ~~`"countries/de"`~~ |
| article type | `"article"` | ~~`"types/article"`~~ |
| SDG 13 | `"13"` | ~~`"sdgs/13"`~~ |
| gold OA | `"gold"` | ~~`"oa-statuses/gold"`~~ |

Why bare:

- **DRY with the column registry.** The registry already owns "what type/namespace
  does this column carry." A value prefix duplicates that → two sources that can
  drift. The `column_id` always travels with the `value` in a LeafFilter, so the
  namespace is always available without inlining it.
- **Native IDs already self-namespace.** `A5023888391` is unambiguously an author
  (the letter prefix `A`/`W`/`I`/`S`/`F`/`T`/… is part of the ID). `authors/…` is
  pure redundancy.
- **Renderers become near-identity.** Bare matches the OXURL filter values today
  (`type:article`, `country_code:de`) and the planned OQL surface, so OQO→URL and
  OQO→OQL stop being "strip the prefix" transforms.

Non-native slugs (`de`, `article`, `13`, `en`) are only ambiguous in isolation;
they are never in isolation — `column_id` disambiguates every one.

Typed values: integers for counts/years, booleans for flags, `null` for
unknown/missing. (See §6 on string-vs-typed in serialization.)

**A value may also be a collection reference.** A `col_…` id (e.g. a user's
"countries in the EU" collection) is a valid bare value; the server resolves it via
the **cross-type collection filter** (`<field>:col_…`). Like a native ID, the
`col_` prefix self-identifies, so it stays bare. This is the slick, shareable way
to express a reusable entity set — e.g. `{column_id: "authorships.countries",
value: "col_eu27"}` instead of a 27-code OR-list. The collection is a saved set of
*entities* (countries, institutions, …) of the type the column expects.

---

## 3. Boolean structure: one unified tree

Boolean logic lives **only** in the tree shape, never inside a `value` string:

- **AND / OR** are `BranchFilter.join`. Top-level `filter_rows` is an implicit AND.
- A `LeafFilter` is a single proposition. Its `value` may carry **inline search
  syntax** for the `contains` operator — `"phrase"` for an exact phrase, `*` / `?`
  for wildcards, `"phrase"~N` for proximity — but **never** `AND`/`OR`/`NOT`; those
  always lift to a `BranchFilter`.

Example — `agile AND (supply chain OR value chain) AND (lead time OR cycle time)`:

```jsonc
{ "get_rows": "works", "filter_rows": [
  { "column_id": "title_and_abstract.search", "value": "agile", "operator": "contains" },
  { "join": "or", "filters": [
      { "column_id": "title_and_abstract.search", "value": "supply chain", "operator": "contains" },
      { "column_id": "title_and_abstract.search", "value": "value chain",  "operator": "contains" } ] },
  { "join": "or", "filters": [
      { "column_id": "title_and_abstract.search", "value": "lead time",  "operator": "contains" },
      { "column_id": "title_and_abstract.search", "value": "cycle time", "operator": "contains" } ] }
] }
```

The same tree can span **different search fields per block** (`display_name.search`,
`title_and_abstract.search`, `default.search`) — `column_id` is per-leaf. (This is
exactly the shape of large real systematic-review strategies.)

### 3.1 Quoting scopes a phrase to one sub-record; `~N` slop widens within it

On the multi-valued affiliation/byline search fields (`raw_affiliation_strings.search`,
`raw_author_name.search`), an **unquoted** multi-word value matches *work-scoped* —
the words may land in *different* affiliations/bylines on the same work. A
**quoted phrase** matches *sub-record-scoped*: ES inserts a large
`position_increment_gap` between the repeated field's values, so a phrase (even
with slop) cannot span two of them. This makes a single `contains` leaf express
true **intra-affiliation co-occurrence**:

- `raw_affiliation_strings.search: "london hospital"~5` — both words in the *same*
  affiliation (the `~5` slop allows order/intervening words within that one string).
- `raw_author_name.search: "john smith"~2` — byline middle-name recall ("John
  Maynard Smith", "John P. Smith") without crossing co-authors.

Caveat: slop is a precision/recall lever — it helps for rare strings and blows up
recall on common ones (`"john smith"~1` ≈ 4× the hits), so apply it adaptively, not
always-on (proven in oxjob #240). The inline `"phrase"~N` syntax is the same one
from §3; this section just records *what it buys you* on the per-record search
fields. (A future ES `nested` mapping would give exact, unbounded-distance
co-occurrence; the quote+slop form is the representable-today answer.)

---

## 4. Negation: the `is_negated` polarity bit

Negation is a boolean **`is_negated`** on every node (`LeafFilter` and
`BranchFilter`). It is the **single** negation mechanism — the old `is not` /
`does not contain` operators were removed. Leaf operators are strictly
affirmative: `is`, `>`, `>=`, `<`, `<=`, `contains`.

- A negated leaf maps 1:1 to the OpenAlex URL per-leaf negation `!`
  (`field:!value`). It renders naturally as "foo is not bar".
- `is_negated` on a branch negates the whole group.

**Canonical form = NNF (negation normal form).** The canonicalizer pushes any
branch-level `is_negated` down to the leaves via De Morgan (flip `and`↔`or`, toggle
child polarity), cancels double negation, then flattens and sorts — so a
*canonical* OQO carries `is_negated` only on leaves (a literal = atom + sign, the
SAT/CNF/BDD standard). The representation permits `is_negated` anywhere; the
canonical form restricts it to leaves.

**Negation is safe / range-restricted**: it is closed-world set-complement *within
the queried entity's result domain*, never absolute complement (relational-calculus
safety / Datalog range-restriction / IR `AND NOT`). The URL `!` is already
entity-scoped.

Example — COVID papers excluding pediatric ones:

```jsonc
{ "get_rows": "works", "filter_rows": [
  { "column_id": "title_and_abstract.search", "value": "covid",     "operator": "contains" },
  { "column_id": "title_and_abstract.search", "value": "pediatric", "operator": "contains", "is_negated": true }
] }
```

---

## 5. Equality, canonicalization, and rendering (three separate layers)

1. **Equality** — the semantic relation: `A OR B ≡ B OR A`; nested same-join groups
   flatten; double negation cancels; De Morgan equivalents are equal. The spec
   *defines* this relation; it is what "two OQOs mean the same query" means.
2. **Canonicalizer** — an optional pure function `OQO → canonical OQO`
   (`query_translation/oqo_canonicalizer.py`). It produces NNF, flattens same-join
   groups, unwraps single-child groups, drops empties, coerces typed leaf values,
   and **sorts** operands within every group + the top level (AND/OR are
   commutative). Used **only** where a stable representation is needed: cache keys,
   hashing, dedup, test fixtures. It **never** replaces the user's OQO. `group_by`
   order is meaningful (dimension order) and is **preserved**, not sorted.
3. **Rendering** — `OQO → URL / OQL` **preserves the user's operand order**. The
   canonicalizer is invoked only when something needs a hash; rendering does not
   canonicalize.

> The canonicalizer sorts operands. Earlier impl did not; it now does (this doc and
> the impl agree). Sorting is safe because it happens only in the canonical form,
> which never feeds rendering.

---

## 6. Serialization: JSON normative, YAML display-only

- **JSON is the normative serialization.** Hash / canonicalize over **JSON, never
  YAML** — YAML emitter quoting/style choices change the bytes at identical
  semantics, which would make hashes unstable.
- **YAML is display/authoring only**, and a YAML rendering **MUST round-trip to
  byte-identical JSON**. The safe direction is JSON→YAML; never treat hand-authored
  YAML as authoritative without re-validating to JSON.
- **Quote every string `value` on emit.** YAML's permissive scalar parsing means
  user-controlled text means something different in YAML vs JSON:
  - the country code `NO` coerces to boolean `false` (the "Norway problem") — and
    still validates against the schema's `string|int|bool|null` union;
  - a leading `*` wildcard (`*gene*`) breaks the YAML parse;
  - a ` #` mid-value silently truncates the scalar (YAML comment);
  - `year: 012` coerces to `10` (octal-ish) / loses the leading zero.
  The fix is **serialization-layer** (quote-on-emit), not schema-layer — a JSON
  Schema cannot catch coercion of a genuine `string|int|bool|null` union.
- **Pin YAML 1.2 core schema** (smaller coercion surface than 1.1; kills
  `yes/no/on/off` and sexagesimal).
- **Per-column typing** (a `column_id → expected value type` map, owned by the
  column registry) is useful defense-in-depth but only *detection-after-parse*: it
  misses wrong-value-same-type coercion (`year: 012`→10) and `#`-truncation, so it
  is **not** a substitute for quote-on-emit.

(The canonicalizer's typed-value coercion in §5 operates on the in-memory dict /
normative JSON, not on display YAML — different layers.)

---

## 7. Column validation lives in a registry, not the dataclass

`LeafFilter.column_id` is intentionally a free `str` — the dataclass is
**column-agnostic**. "Is this column valid on this entity? what value type? which
operators?" is answered by a separate **column registry**, not by the OQO schema.

- Current home of the registry: `openalex-gui/src/facetConfigs.js`.
- A server-side copy (for validating OQO server-side) and the registry population
  are tracked in oxjob **#294** (`column-registry-sync`). #284 ships the spec that
  *names* the registry; #294 builds the thing it references.

This is why §2 (bare values) works: the registry is the single type/namespace
authority, so the value doesn't need to carry a prefix.

---

## 8. Stage B: `group_by` as a list

`group_by` is a **list** of `GroupBy` dimensions, so multi-dimensional grouping
(e.g. topic × year) is expressible in the spec:

```jsonc
{ "get_rows": "works",
  "filter_rows": [ { "column_id": "publication_year", "value": 1976, "operator": ">=" } ],
  "group_by":    [ { "column_id": "primary_topic.id" }, { "column_id": "publication_year" } ] }
```

Dimension order is meaningful and is preserved by the canonicalizer.

**Live-impl gaps (spec is ahead of the server — deliberately):**

- Multi-dimensional `group_by` (>1 dimension) is single-dimension only in the live
  serving impl → **#297** (`group-by-extensions`).
- Sorting groups by an aggregate metric (e.g. funders by mean citation impact) is
  out of scope here (adjacent to Stage C) → **#297**. **Group buckets always
  auto-sort by `_count` descending (= works_count desc) by default**; a `sort_by`
  alongside `group_by` may only re-order buckets via the synthetic `count` / `key`
  keys — a `sort_by` naming a *real* column under a `group_by` is **not** supported
  (it orders rows, which don't exist in a grouped response) and is treated as
  ignored. The NL→OQO agent (oxjob #344) therefore OMITS `sort_by` when it emits a
  `group_by`; supporting real-column bucket ordering was scoped and deferred as
  non-trivial (sub-aggregation wiring across buckets.py / sort.py / validator.py —
  oxjob #344 decision 3).

---

## 9. Documented `/works` default: `is_xpac:false`

Every `/works` request to the walden index silently excludes `is_xpac:true` works
unless the caller passes `&include_xpac=true` (`works/views.py`). The OQO spec
**acknowledges this as part of `/works` semantics** — a documented default of the
works domain, not a per-query flag. It does not push to flip the API default (a
separate product decision). Consumers translating "all works" NL should be aware
the default universe is narrowed.

---

## 10. Known impl lag (this round shipped the *spec core*)

#284 shipped the spec-defining files: the `oqo.py` dataclass, the generated
`oqo-schema.json`, the `oqo_canonicalizer.py` canonical form, and this prose. The
translation impl in `query_translation/` (`oql_parser`, `oql_renderer`,
`url_parser`, `url_renderer`, `validator`, and their tests) still references the
removed operators and does not yet thread `is_negated` / `group_by`. That endpoint
(`/query`) is not wired into the live OXURL serving path and is unreachable via the
public proxy, so the lag is safe; updating it is the implementation follow-up.
