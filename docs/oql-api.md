# The OQL API

**Everything OQL does is available over plain HTTP, no GUI required.** There are two
endpoint families, and they divide cleanly:

- **Execute**: send a query, get results back. Lives at the **API root**:
  `GET /?oql=…`, `GET /?oqo=…`, or `POST /` with a JSON body.
- **Translate**: convert a query between its three forms (OQL text, OQO JSON, classic
  URL) and validate it, *without running it*. Lives at **`/query`**.

Every response also carries **`meta.x_query`**, which echoes your query back in all three
forms, so any result you get is also a lesson in how to write the next query.

> Every example on this page runs on production today. Counts are live and will drift.

---

## The 30-second version

```
# Run an OQL query (the API root, not /works: the query names what it gets):
curl -G "https://api.openalex.org/" --data-urlencode "oql=get works from 2020"

# Translate a query between forms without running it (free):
curl "https://api.openalex.org/query/oql/get%20works%20from%202020"

# Long query? POST it: no length limit:
curl -X POST "https://api.openalex.org/" \
  -H "Content-Type: application/json" \
  -d '{"oql": "get works from 2020"}'
```

The rest of this page is detail: each surface, its parameters, its response shape, and its
errors. The language itself is in the [OQL guide](https://help.openalex.org/access/oql/).

---

## The three query formats

Every query can be written three ways. They share one meaning but differ in syntax and in
how much they can express:

| Format | Looks like | Reach for it when |
|---|---|---|
| **Classic URL** | `/works?filter=publication_year:2020` | you want backwards compatibility with the API you already know |
| **OQL** | `get works from 2020` | you're writing most applications: it reads and writes like a sentence |
| **OQO** | `{"get_rows": "works", "filter_rows": […]}` | you're building queries from a program or an agent: it's JSON with a concrete, validatable [schema](https://api.openalex.org/query/spec/schema) |

How they relate:

- **OQL and OQO are two faces of the same thing.** Every OQL query has exactly one OQO and
  vice versa: same meaning, different syntax. **OQO is the canonical internal
  representation**: everything you send, in any format, is compiled to an OQO before it runs.
- **The classic URL is less expressive.** Every URL maps to a corresponding OQL and OQO, but
  **not the reverse**: many OQL/OQO queries (rich boolean nesting, proximity, tables of
  groups with numbers) have no classic URL. That's deliberate: OQL and OQO widen the space
  of questions you can ask.

So: use the **classic URL** for legacy compatibility, **OQL** for most applications, and
**OQO** when an agent or program needs a JSON schema to validate against. The
[`/query` endpoint](#translating-a-query-the-query-endpoint) converts freely between all
three, and every result echoes all three back in [`meta.x_query`](#reading-results-meta-x-query).

---

## Running a query

### GET /?oql=

Put a URL-encoded OQL string in the `oql` parameter **at the API root**:

```
https://api.openalex.org/?oql=get works from 2020
```

```
curl -G "https://api.openalex.org/" \
  --data-urlencode "oql=get works since 2020 with cancer in the title, most cited first" \
  --data-urlencode "per-page=5"
```

Two things to know:

- **The root, not `/works`.** An OQL query names what it gets (`get works …`,
  `get authors …`, `get the count of works …`), so there's one execution endpoint for
  everything. `GET /works?oql=…` is an **error** (400, "oql is not a valid parameter").
- **The response is the standard envelope.** A list comes back as the same `{meta, results}`
  you get from `/works?filter=…`, with the same entity objects; existing client code doesn't
  need to change.

**A table of groups** comes back with a `group_by` array, one row per group, and a `summary`
of the whole set:

```
curl -G "https://api.openalex.org/" \
  --data-urlencode "oql=get the count and mean FWCI of [Kenya](KE)'s works by year since 2020"
```

```json
{
  "meta": {"count": 92151, "groups_count": 7, "more_groups": false,
           "measures": [{"key": "count", "oql": "count"}, {"key": "mean_fwci", "oql": "mean FWCI"}],
           "splits": [{"oql": "year", "column_id": "publication_year"}], "…": "…"},
  "summary": {"all": {"key": "all", "key_display_name": "all works", "count": 92151, "mean_fwci": 1.8348}},
  "group_by": [{"key": "2020", "key_display_name": "2020", "count": 11395, "mean_fwci": 1.9919}, "…"]
}
```

Each group row has `key`, `key_display_name`, and one field per number (`count`,
`mean_fwci`, `percent_open_access_is_oa`, …; `meta.measures` maps each field to its OQL
words, and `meta.splits` describes each split). With two splits, each outer row holds its
inner groups in a `groups` array (the CSV export flattens them to one row per pair). The
`summary` has `all`, the whole set in one row, and with two splits `splits`, each split's
groups on their own. A number in the summary is computed from the works, never added up
from the rows.

The paging and view parameters work alongside `oql`:

| Parameter | Works with `?oql=` | Notes |
|---|---|---|
| `per-page`, `page` | yes | basic paging |
| `cursor` | yes | deep paging; start with `cursor=*`, follow `meta.next_cursor` |
| `sort` | yes | classic `sort=column:direction`, e.g. `sort=cited_by_count:desc`. It's written into the query: `meta.x_query.oql` comes back with the order phrase (`, most cited first`). |
| `select` | yes | classic `select=field,field` to project a subset of fields |
| `rerank` | yes | `rerank=true` reorders the top 100 of a relevance-sorted works search by relevance; result 101 onward is unchanged. Adds 10 credits. See [Rerank](https://help.openalex.org/api/searching/#rerank) |
| `format` | yes | `format=csv` on a table of groups returns its groups as one flat CSV: one row per group, a column per split, a column per number. A single split by a field pages: add `cursor=*` and follow the `X-Next-Cursor` header (10,000 groups a page); without a cursor it holds the first 10,000. Costs the query's price for every 100 rows |
| `table` | yes | with `format=csv`: `table=summary` returns the summary instead: `all-works.csv` (the whole set, one row), and with two splits a zip of it plus `by-<split>.csv` for each split's groups on their own. Default `groups` |
| `api_key` | yes | or send `Authorization: Bearer <key>` (see Auth below) |

**The order is part of the query; field selection and paging are not.** OQL says which rows
and in what order (`get works about kelp, most cited first`), and the OQO carries the order
as `sort_by`. A sibling `sort=` still works and wins: it's written into the query, so the
echo always shows the order you got. `select`, `page`, `per-page` and `cursor` are view
parameters that travel beside the query: the classic query-string parameters above, on
either verb, or top-level body keys on POST (below).

### GET /?oqo=

OQO (the OpenAlex Query Object) is the JSON form of the same query: what OQL compiles to,
and the natural form when a *program* is building queries. Send it URL-encoded in the `oqo`
parameter, again at the root:

```
curl -G "https://api.openalex.org/" \
  --data-urlencode 'oqo={"get_rows": "works", "filter_rows": [{"column_id": "publication_year", "value": 2020}]}' \
  --data-urlencode "per-page=1"
```

The OQO carries the query itself: filters, splits and numbers, the order, and sampling.
Projection and paging are **not** in the object: put them in the URL parameters as above.
See [The OQO object](#the-oqo-object) below for the shape.

### POST /

GET puts the whole query in the request line, which is capped at 8,190 bytes; a big
Boolean query can blow past that. `POST /` takes the same query in a JSON body, with **no
length limit**:

```
curl -X POST "https://api.openalex.org/?per-page=5" \
  -H "Content-Type: application/json" \
  -d '{"oql": "get works from 2020"}'
```

or with an OQO, view params riding as sibling body keys:

```
curl -X POST "https://api.openalex.org/" \
  -H "Content-Type: application/json" \
  -d '{"oqo": {"get_rows": "works",
               "filter_rows": [{"column_id": "publication_year", "value": 2020}],
               "sort_by": [{"column_id": "cited_by_count", "direction": "desc"}]},
       "select": "id,display_name,cited_by_count",
       "per_page": 5}'
```

Rules of the road:

- The body is a JSON object with **exactly one** of `"oql"` or `"oqo"`, plus optionally the
  sibling params `sort` / `select` / `page` / `per_page` / `cursor`, `"rerank": true`, and
  `"format": "csv"` with optional `"table": "summary"` (a table of groups, as a CSV). Any
  other top-level key is a **400** (`invalid_body`), and so is sending both `oql` and `oqo`.
  `Content-Type: application/json` is required (without it: 400, `invalid_body`).
- Sibling params use the same classic syntax as the query-string form: `sort` is a string
  like `"cited_by_count:desc,display_name"`, `select` a comma-string (a JSON list of column
  names also works in the body), `page`/`per_page` integers, `cursor` a string. Body siblings
  win over query-string siblings, which win over the order inside the OQO.
- `sample`/`seed` belong **inside the OQO**: they change which rows you get, not how
  they're presented; `{"oql": "…", "sample": 5}` is rejected.

### Errors

A query that doesn't parse or validate returns **400** with a structured `validation`
object, never a silent empty result:

```
curl -G "https://api.openalex.org/" --data-urlencode "oql=get works where yearx is 2020"
```

```json
{
  "validation": {
    "valid": false,
    "errors": [
      {
        "type": "parse_error",
        "message": "unknown field \"yearx\"  Fix: check the field name against the properties registry",
        "position": 16,
        "context": "get works where yearx is 2020",
        "location": null
      }
    ],
    "warnings": []
  }
}
```

`type` is one of `parse_error`, `bad_request`, `invalid_entity`, `invalid_body`,
`invalid_column`, `invalid_measure`, `query_too_slow`. Parse errors include the character `position` and the
offending `context`, and the `message` usually ends with a concrete `Fix:` in OQL's own
words (`unknown split by FWCI  Fix: a table splits by author, company, …`).

### Auth and cost

No API key is required. These endpoints follow the same rules as the rest of the API: a
free-account key raises your daily credit budget. A list costs what the same query costs as
a URL: 1 credit, or 10 with a search, so an OQL search costs what `/works?search=` costs. A
table of groups, and anything in OQL's general form, is priced from what it does: its set of
works costs what a list costs (1 credit, or 10 with a search), plus 1 for each lookup of the
groups' own records and 10 for each compared search (see
[Example costs](https://help.openalex.org/access/example-costs/#what-an-oql-calculation-costs)).
The response's `meta.cost` shows what each call cost. `/query` is free and shows a query's
price before you run it (`check.cost`). Authenticate with either form:

```
curl -G "https://api.openalex.org/" \
  -H "Authorization: Bearer YOUR_API_KEY" \
  --data-urlencode "oql=get works from 2020"
```

or append `&api_key=YOUR_API_KEY`.

---

## Translating a query: the /query endpoint

The same query has three interchangeable forms (see
[The three query formats](#the-three-query-formats) above for when to use which):

| Form | Looks like | Best for |
|---|---|---|
| `oql` | `get works from 2020` | humans reading and writing |
| `oqo` | `{"get_rows": "works", "filter_rows": […]}` | programs and agents building queries |
| `oxurl` | `/works?filter=publication_year:2020` | the classic API you already know |

`/query` converts any form into all the others, and validates it, **without executing
anything** (it never touches the search index, and costs nothing). It's the machinery
behind the website's OQL tab, and it's how a tool of your own can offer OQL input or output.
Whatever OQL you send, it comes back in canonical form: send `works where year is (2020)
group by type` and `oql` says `get the count of works from 2020 by type`.

Because OQL and OQO are equally expressive, translating between them always round-trips
cleanly. Translating **into** `oxurl` can fail, though: the classic URL grammar can't
represent every OQL/OQO query (deeply nested booleans, proximity search, tables of groups).
When that happens `/query` returns the `oql`/`oqo`/`validation` fields and sets `oxurl` to
`null`: the query is still perfectly valid and runnable, it just has no URL spelling.

### GET /query/oql, /query/oqo, /query/oxurl

Put the query in the path (URL-encoded or plain):

```
curl "https://api.openalex.org/query/oql/get%20works%20from%202020"
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

```json
{
  "oxurl": "/works?filter=publication_year:2020",
  "oql": "get works from 2020",
  "oql_oneline": "get works from 2020",
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
| `oxurl` | the classic-URL form: `null` when the query can't be expressed as one |
| `oql` | the canonical OQL: a sentence (`get works …`, `get the count of works … by …`), or OQL's general form when no sentence can say the query |
| `oql_oneline` | the same, on one line |
| `oql_render_v2` | a rich render tree (every token with its role and metadata), for building editors and syntax highlighters; most clients can ignore it |
| `oqo` | the canonical OQO: parse any form, read this one |
| `validation` | `{valid, errors, warnings}`, same shape as execution errors above |
| `check` | for a table of groups or the general form: the time estimate (`check.estimate`) and the price, step by step (`check.cost`) |

A response may also carry `x_new_oql`; it now always equals `oql`, so read `oql`. Bad input
gets a 400 with the same `validation` object as the execution endpoints. A query that
*parses* but fails validation returns 400 with the `oqo` included, so you can see what it
understood.

---

## Reading results: meta.x_query

Every list or group response, including from **classic** `/works?filter=…` calls, carries
an `x_query` object in `meta`, echoing the query in all three forms:

```
curl "https://api.openalex.org/works?filter=publication_year:2020&per-page=1"
```

```json
"meta": {
  "count": 11446647,
  "x_query": {
    "oql": "get works from 2020",
    "oqo": {"get_rows": "works", "filter_rows": [{"column_id": "publication_year", "value": 2020}]},
    "url": "/works?filter=publication_year:2020&per_page=1",
    "order": "most cited (age-adjusted) first",
    "order_default": true
  }
}
```

What it's for:

- **Learn OQL from queries you already have**: hit any classic URL and read the `oql`
  field back.
- **Round-trip**: feed `x_query.oqo` back to `POST /` (or `x_query.oql` to `?oql=`) and
  get the same results; modify it programmatically along the way.
- **Interoperate**: a tool that stores `x_query.oqo` can rebuild the query in whichever
  surface it wants: OQL text, a classic URL, or the website.

`url` is `null` when the query has no classic-URL equivalent. `order` is the order the
results came back in, in OQL's words, and `order_default` says whether that's the default
(so the OQL leaves it out). On classic calls the translation is best-effort: a handful of
exotic parameter combinations don't round-trip.

> The `x_` prefix means what it usually does: this field is young and its details may
> still shift. The three-forms concept is stable; treat exact field-level details as
> subject to change.

---

## The OQO object

The full, formal shape is the JSON Schema on the **OQO schema** page (served at
`/query/spec/oqo`). The short version, top level:

| Key | Type | Meaning |
|---|---|---|
| `get_rows` | string, **required** | what to return: `works`, `authors`, `institutions`, … |
| `filter_rows` | array of filter nodes | the filters; top-level entries are AND-ed |
| `corpus` | `core` \| `expansion` \| `all` | which works corpus (works only; default `core`) |
| `sort_by` | array of `{column_id, direction}` | the order (`, most cited first` is `[{"column_id": "cited_by_count", "direction": "desc"}]`) |
| `group_by` | array of `{column_id}`, each with an optional `where` | the splits of a table of groups; `where` holds a count floor (`Only …`) |
| `calculate` | array of `{measure, column_id}` | the numbers of a table (`count`, `mean` of `fwci`, `value` of a group's own field such as `summary_stats.h_index`) |
| `sample` | int | random sample of n results (optional `seed`, a string, for reproducibility) |

Projection and paging are **sibling request params** (`select`, `page`, `per_page`,
`cursor`: see "Rules of the road" above), not OQO keys.

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
- A **branch** is `{join: "and"|"or", filters: […]}`, nesting to any depth: this is where
  OQO exceeds the classic URL syntax, which can't nest.

A table of groups, `get the count and mean FWCI of works about kelp by country, highest mean
FWCI first. Only countries with at least 50 works about kelp.`, is:

```json
{
  "get_rows": "works",
  "filter_rows": [{"column_id": "title_abstract_keywords.search", "value": "kelp", "operator": "has"}],
  "group_by": [{"column_id": "authorships.countries",
                "where": {"measure": "count", "operator": ">=", "value": 50}}],
  "calculate": [{"measure": "count"}, {"measure": "mean", "column_id": "fwci"}],
  "sort_by": [{"column_id": "mean_fwci", "direction": "desc"}]
}
```

Putting it together: "recent works about cancer that are open access or reviews, most
cited first":

```
curl -X POST "https://api.openalex.org/" \
  -H "Content-Type: application/json" \
  -d '{"oqo": {
        "get_rows": "works",
        "filter_rows": [
          {"column_id": "title_abstract_keywords.search", "value": "cancer", "operator": "has"},
          {"column_id": "publication_year", "value": 2020, "operator": ">="},
          {"join": "or", "filters": [
            {"column_id": "open_access.is_oa", "value": true},
            {"column_id": "type", "value": "review"}
          ]}
        ],
        "sort_by": [{"column_id": "cited_by_count", "direction": "desc"}]
      },
      "select": "id,display_name,cited_by_count",
      "per_page": 5}'
```

Column ids are the machine names from the **properties registry**: list them at
`https://api.openalex.org/properties` (or per entity: `/properties/works`). The OQL name
and the column id often differ (`year` ↔ `publication_year`); when in doubt, write the
query in OQL, translate it, and read the `oqo`.

---

## Related endpoints

| Endpoint | What it does |
|---|---|
| `GET /validate?q=<oql>` | lint an OQL string; always 200; returns rich `diagnostics` with stable error codes, spans, and fix-its, built for editors |
| `GET /parse-context?q=<oql>&pos=<n>` | what the grammar expects at a cursor position, built for autocomplete |
| `GET /query/orders?q=<oql>` | the orders a query can take, in OQL's words, and which one is the default |
| `GET /properties`, `/properties/<entity>` | the registry of every queryable column, its operators, and its OQL name |
| `GET /query/spec` | index of the spec artifacts (cheat sheet, guide, spec, OQO schema, grammar) that power these docs pages |

And the rest of the story lives in the sibling pages here under **`/query`**: the **Cheat
sheet** and **Guide** teach the OQL language itself, the **Spec** is the normative
reference, and the **OQO schema** page renders the full JSON Schema.

OQL and its API are under active development: tell us what's confusing, what's missing,
and what you wish you could do.
