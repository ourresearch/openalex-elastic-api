# The OQL API

**Everything OQL does is available over plain HTTP — no GUI required.** There are two
endpoint families, and they divide cleanly:

- **Execute** — send a query, get entity results back. Lives at the **API root**:
  `GET /?oql=…`, `GET /?oqo=…`, or `POST /` with a JSON body.
- **Translate** — convert a query between its three forms (OQL text, OQO JSON, classic
  URL) and validate it, *without running it*. Lives at **`/query`**.

Every response also carries **`meta.x_query`**, which echoes your query back in all three
forms — so any result you get is also a lesson in how to write the next query.

> Every example on this page runs on production today. Counts are live and will drift.

---

## The 30-second version

```
# Run an OQL query (the API root, not /works — the query names its own entity):
curl -G "https://api.openalex.org/" --data-urlencode "oql=works where year is (2020)"

# Translate a query between forms without running it:
curl "https://api.openalex.org/query/oql/works%20where%20year%20is%20(2020)"

# Long query? POST it — no length limit:
curl -X POST "https://api.openalex.org/" \
  -H "Content-Type: application/json" \
  -d '{"oql": "works where year is (2020)"}'
```

The rest of this page is detail: each surface, its parameters, its response shape, and its
errors.

---

## Running a query

### GET /?oql=

Put a URL-encoded OQL string in the `oql` parameter **at the API root**:

```
https://api.openalex.org/?oql=works where year is (2020)
```

```
curl -G "https://api.openalex.org/" \
  --data-urlencode "oql=works where title has (cancer) and year >= (2020)" \
  --data-urlencode "per-page=5"
```

Two things to know:

- **The root, not `/works`.** An OQL query names its own entity (`works where …`,
  `authors where …`), so there's one execution endpoint for all entities.
  `GET /works?oql=…` is an **error** (400, "oql is not a valid parameter").
- **The response is the standard envelope** — the same `{meta, results}` (or
  `{meta, group_by}`) you get from `/works?filter=…`, with the same entity objects.
  Existing client code doesn't need to change.

The paging parameters work alongside `oql`:

| Parameter | Works with `?oql=` | Notes |
|---|---|---|
| `per-page`, `page` | yes | basic paging |
| `cursor` | yes | deep paging; start with `cursor=*`, follow `meta.next_cursor` |
| `sort` | yes | classic `sort=column:direction` (comma-separated for tiebreakers), e.g. `sort=cited_by_count:desc` |
| `select` | yes | classic `select=field,field` to project a subset of fields |
| `api_key` | yes | or send `Authorization: Bearer <key>` (see Auth below) |

**Sorting and field selection are the OQO's job**, but the classic `?sort=`/`?select=`
parameters still work next to `?oql=`/`?oqo=` for convenience — they're folded into the query
as `sort_by`/`select`. If the OQO already carries a `sort_by`/`select`, the object wins and the
matching query-string parameter is ignored (same precedence as `per_page`/`seed`). The
canonical form is to put `sort_by`/`select` inside the OQO (examples below), and that's what
`meta.x_query` always echoes back.

Grouping *is* part of the language — write it in the query:

```
curl -G "https://api.openalex.org/" \
  --data-urlencode "oql=works where year is (2020) group by type"
```

…and the response comes back with a `group_by` array instead of `results`.

### GET /?oqo=

OQO (the OpenAlex Query Object) is the JSON form of the same query — what OQL compiles to,
and the natural form when a *program* is building queries. Send it URL-encoded in the `oqo`
parameter, again at the root:

```
curl -G "https://api.openalex.org/" \
  --data-urlencode 'oqo={"get_rows": "works", "filter_rows": [{"column_id": "publication_year", "value": 2020}]}' \
  --data-urlencode "per-page=1"
```

An OQO can be fully **self-contained**: paging, sorting, and projection can live inside the
object itself (`per_page`, `page`, `cursor`, `sort_by`, `select`, `sample`, `seed`) instead
of in URL parameters. See "The OQO object" below for the shape.

### POST /

GET puts the whole query in the request line, which is capped at 8,190 bytes — a big
Boolean query can blow past that. `POST /` takes the same query in a JSON body, with **no
length limit**:

```
curl -X POST "https://api.openalex.org/?per-page=5" \
  -H "Content-Type: application/json" \
  -d '{"oql": "works where year is (2020)"}'
```

or with an OQO:

```
curl -X POST "https://api.openalex.org/" \
  -H "Content-Type: application/json" \
  -d '{"oqo": {"get_rows": "works",
               "filter_rows": [{"column_id": "publication_year", "value": 2020}],
               "sort_by": [{"column_id": "cited_by_count", "direction": "desc"}],
               "select": ["id", "display_name", "cited_by_count"],
               "per_page": 5}}'
```

Rules of the road:

- The body is a JSON object with **one** of `"oql"` or `"oqo"`. `Content-Type:
  application/json` is required (without it: 400, `invalid_body`).
- Paging/sorting options go in the **URL query string** (as with GET) or **inside the OQO**
  — *not* as extra top-level body keys. `{"oql": "…", "per_page": 5}` silently ignores the
  `per_page`; `{"oqo": {…, "per_page": 5}}` honors it.

### Errors

A query that doesn't parse or validate returns **400** with a structured `validation`
object — never a silent empty result:

```
curl -G "https://api.openalex.org/" --data-urlencode "oql=works where yearx is (2020)"
```

```json
{
  "validation": {
    "valid": false,
    "errors": [
      {
        "type": "parse_error",
        "message": "unknown field \"yearx\"  Fix: check the field name against the properties registry",
        "position": 12,
        "context": "works where yearx is (2020)",
        "location": null
      }
    ],
    "warnings": []
  }
}
```

`type` is one of `parse_error`, `bad_request`, `invalid_entity`, `invalid_body`. Parse
errors include the character `position` and the offending `context`, and the `message`
usually ends with a concrete `Fix:`.

### Auth and cost

No API key is required — these endpoints follow the same rules as the rest of the API: a
free-account key raises your daily credit budget, and a query here costs the same credits
as its classic-URL equivalent (the response's `meta.cost_usd` shows what each call cost).
Authenticate with either form:

```
curl -G "https://api.openalex.org/" \
  -H "Authorization: Bearer YOUR_API_KEY" \
  --data-urlencode "oql=works where year is (2020)"
```

or append `&api_key=YOUR_API_KEY`.

---

## Translating a query: the /query endpoint

The same query has three interchangeable forms:

| Form | Looks like | Best for |
|---|---|---|
| `oql` | `works where year is (2020)` | humans reading and writing |
| `oqo` | `{"get_rows": "works", "filter_rows": […]}` | programs building queries |
| `oxurl` | `/works?filter=publication_year:2020` | the classic API you already know |

`/query` converts any form into all the others, and validates it — **without executing
anything** (it never touches the search index, and costs nothing). It's the machinery
behind the GUI's OQL tab, and it's how a tool of your own can offer OQL input or output.

### GET /query/oql, /query/oqo, /query/oxurl

Put the query in the path (URL-encoded or plain):

```
curl "https://api.openalex.org/query/oql/works%20where%20year%20is%20(2020)"
curl "https://api.openalex.org/query/oxurl/works?filter=publication_year:2020"
curl "https://api.openalex.org/query/oqo/%7B%22get_rows%22%3A%22works%22%7D"
```

### POST /query

Same 8,190-byte request-line cap as above; same escape hatch. The body takes exactly one
of the three forms:

```
curl -X POST "https://api.openalex.org/query" \
  -H "Content-Type: application/json" \
  -d '{"oxurl": "/works?filter=publication_year:2020"}'
```

### The translation response

Every `/query` translation returns the same six fields:

```json
{
  "oxurl": "/works?filter=publication_year:2020",
  "oql": "works where year is (2020)",
  "oql_oneline": "works where year is (2020)",
  "oql_render_v2": { "…": "…" },
  "oqo": {
    "get_rows": "works",
    "filter_rows": [{"column_id": "publication_year", "value": 2020}]
  },
  "validation": {"valid": true, "errors": [], "warnings": []}
}
```

| Field | What it is |
|---|---|
| `oxurl` | the classic-URL form — `null` when the query can't be expressed as one (e.g. nested boolean logic the URL syntax can't nest) |
| `oql` | the canonical OQL rendering (line-wrapped for readability on big queries) |
| `oql_oneline` | the same rendering forced onto one line |
| `oql_render_v2` | a rich render tree (every token with its role and metadata) — for building editors and syntax highlighters; most clients can ignore it |
| `oqo` | the canonical OQO — parse any form, read this one |
| `validation` | `{valid, errors, warnings}`, same shape as execution errors above |

Bad input gets a 400 with the same `validation` object as the execution endpoints. A query
that *parses* but fails validation returns 400 with the `oqo` included, so you can see what
it understood.

---

## Reading results: meta.x_query

Every list or group response — including from **classic** `/works?filter=…` calls —
carries an `x_query` object in `meta`, echoing the query in all three forms:

```
curl "https://api.openalex.org/works?filter=publication_year:2020&per-page=1"
```

```json
"meta": {
  "count": 11446647,
  "x_query": {
    "oql": "works where year is (2020)",
    "oqo": {"get_rows": "works", "filter_rows": [{"column_id": "publication_year", "value": 2020}], "per_page": 1},
    "url": "/works?filter=publication_year:2020&per_page=1"
  }
}
```

What it's for:

- **Learn OQL from queries you already have** — hit any classic URL and read the `oql`
  field back.
- **Round-trip** — feed `x_query.oqo` back to `POST /` (or `x_query.oql` to `?oql=`) and
  get the same results; modify it programmatically along the way.
- **Interoperate** — a tool that stores `x_query.oqo` can rebuild the query in whichever
  surface it wants: OQL text, a classic URL, or the GUI.

`url` is `null` when the query has no classic-URL equivalent. On classic calls the
translation is best-effort — a handful of exotic parameter combinations don't round-trip.

> The `x_` prefix means what it usually does: this field is young and its details may
> still shift. The three-forms concept is stable; treat exact field-level details as
> alpha, like the rest of OQL.

---

## The OQO object

The full, formal shape is the JSON Schema on the **OQO schema** page (served at
`/query/spec/oqo`). The short version — top level:

| Key | Type | Meaning |
|---|---|---|
| `get_rows` | string, **required** | the entity to return: `works`, `authors`, `institutions`, … |
| `filter_rows` | array of filter nodes | the filters; top-level entries are AND-ed |
| `corpus` | `core` \| `expansion` \| `all` | which works corpus (works only; default `core`) |
| `group_by` | array of `{column_id}` | group results into buckets |
| `sort_by` | array of `{column_id, direction, aggregate?}` | result order (`aggregate` = `mean`/`sum`/`min`/`max`, for sorting group buckets by a metric) |
| `select` | array of column ids | project result fields |
| `sample` | int | random sample of n results (optional `seed`, a string, for reproducibility) |
| `per_page`, `page`, `cursor` | paging | so an OQO can be fully self-contained |

A **filter node** is either a leaf or a branch:

```json
{"column_id": "publication_year", "value": 2020, "operator": ">="}

{"join": "or", "filters": [
  {"column_id": "open_access.is_oa", "value": true},
  {"column_id": "type", "value": "review"}
]}
```

- A **leaf** is `{column_id, value}` plus optional `operator` (default `is`; also `>`,
  `>=`, `<`, `<=`, `has` for text search, `in collection`) and `is_negated: true` for
  negation.
- A **branch** is `{join: "and"|"or", filters: […]}`, nesting to any depth — this is where
  OQO exceeds the classic URL syntax, which can't nest.

Putting it together — "highly-cited recent works about cancer that are OA or reviews,
top-cited first":

```
curl -X POST "https://api.openalex.org/" \
  -H "Content-Type: application/json" \
  -d '{"oqo": {
        "get_rows": "works",
        "filter_rows": [
          {"column_id": "default.search", "value": "cancer", "operator": "has"},
          {"column_id": "publication_year", "value": 2020, "operator": ">="},
          {"join": "or", "filters": [
            {"column_id": "open_access.is_oa", "value": true},
            {"column_id": "type", "value": "review"}
          ]}
        ],
        "sort_by": [{"column_id": "cited_by_count", "direction": "desc"}],
        "select": ["id", "display_name", "cited_by_count"],
        "per_page": 5
      }}'
```

Column ids are the machine names from the **properties registry** — list them at
`https://api.openalex.org/properties` (or per entity: `/properties/works`). The OQL name
and the column id often differ (`year` ↔ `publication_year`); when in doubt, write the
query in OQL, translate it, and read the `oqo`.

---

## Related endpoints

| Endpoint | What it does |
|---|---|
| `GET /validate?q=<oql>` | lint an OQL string; always 200; returns rich `diagnostics` with stable error codes, spans, and fix-its — built for editors |
| `GET /parse-context?q=<oql>&pos=<n>` | what the grammar expects at a cursor position — built for autocomplete |
| `GET /properties`, `/properties/<entity>` | the registry of every queryable column, its operators, and its OQL name |
| `GET /query/spec` | index of the spec artifacts (cheat sheet, guide, spec, OQO schema, grammar) that power these docs pages |

And the rest of the story lives in the sibling pages here under **`/query`**: the **Cheat
sheet** and **Guide** teach the OQL language itself, the **Spec** is the normative
reference, and the **OQO schema** page renders the full JSON Schema.

OQL and its API are in alpha and under active development — tell us what's confusing,
what's missing, and what you wish you could do.
