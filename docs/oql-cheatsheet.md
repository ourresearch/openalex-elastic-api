# OQL cheat sheet

**OQL** is the OpenAlex Query Language: a readable way to write any OpenAlex query, from a
simple search to a breakdown with calculations. A query is a series of steps, each starting
with a verb: `get works where title has (cancer) and year >= (2020); then group those works by
year; then, summarize using count, mean FWCI`. Try it in the **OQL tab** at the top of the search
page, or call the API: `https://api.openalex.org/?oql=<your query>`. Checking a query is
free: `https://api.openalex.org/query/oql/<your query>` says whether it's valid, how long it
should take and what it costs, without running it.

> Every example below runs on production today. Counts are live and will drift.

---

## The shape

```
get <things> where <conditions>
  [; then group those <things> by <field> [where <group filter>]]   up to three splits
  [; then, summarize using <calculation>, <calculation>]             always last
```

- **get**: what you start from: `works`, `authors`, `institutions`, `sources`, `funders`, `topics`, ...
- **where**: your conditions (skip it for everything: `get works`).
- A condition is `<field> <operator> (<value>)`: `year >= (2020)`, `type is (review)`, `title has (cancer)`. The value always sits in `( ... )`.
- Steps join with `; then`. Older forms (`works where ... group by year`) still work and are echoed back in this form.

```
get works
get works where year is (2020)
get authors where last known institution is (I136199984 [Harvard University])
```

---

## Filter on a field: `is`, `is not`, `>=`, `<=`, `>`, `<`

| Example | Meaning |
|---|---|
| `get works where year is (2020)` | exact match |
| `get works where type is (article or review)` | one of several: join values with `or` |
| `get works where type is not (review)` | anything but: negate on the verb |
| `get works where citation count >= (100)` | numeric comparison |
| `get works where year >= (2019) and year <= (2023)` | a range = two endpoint filters |
| `get works where institution is (I136199984 [Harvard University])` | entities use their OpenAlex ID; the `[name]` is optional, for reading |
| `get works where institution is in (col_abc123)` | a saved collection; `is not in (...)` excludes it |

---

## Search text: `has`

Search a text field with **`has`**. Inside the parentheses goes a portable search string,
with capital `AND`, `OR`, `NOT`, exactly as you'd publish it in a methods section. Bare words
are **stemmed** (`cancer` also matches *cancers*); **quotes** make an **exact** phrase.

| Example | Meaning |
|---|---|
| `get works where title has (cancer)` | one stemmed word |
| `get works where title has ("climate change")` | exact phrase |
| `get works where title-abstract has ((asthma OR wheeze) NOT (child OR pediatric))` | a full boolean search string |
| `get works where title has ("psoriat*")` | wildcard, quoted; `*` any characters, `?` exactly one |
| `get works where title has (within 3 ("smart", "phone"))` | proximity: terms within N words, any order |
| `get works where title-abstract is similar to ("ocean acidification on coral")` | semantic (meaning-based) search |

**Text fields:** `title`, `abstract`, `title-abstract`, `title-abstract-keywords`, `full text`, `raw affiliation`.

---

## Combine and nest: `and`, `or`, `( ... )`

```
get works where title has (cancer) and year >= (2020)
get works where institution is (I136199984) or funder is (F4320332161)
get works where (year < (2000) and title-abstract has ("global warming"))
  or (title-abstract has ("climate change") and year > (2020))
```

---

## Split into groups: `group those works by`

```
get works where year >= (2020); then group those works by topic
get works where institution is (I63966007); then group those works by year; then group those works again by type
get works where topic is (T10878); then group those works by institution in (I63966007, I97018004, I136199984)
get works where year >= (2010); then group those works by title-abstract search in (("edge AI"), ("neuromorphic computing"))
get works where year >= (2016); then group those works into ((institution is (I99464096)), (country is (BE)))
get works where institution is (I63966007); then group those works into citation count bins at (1, 10, 100)
```

Splits by a field, by listed values (up to 100), by searches (up to 100, at most 5 AND/OR/NOT
each), by conditions (compare sets, or periods), or into bins (`bins at (...)` or `bins of
(10)`). A yes/no field gives two groups: `open access` and `not open access`. Every grouped
result also has a **total row** for the whole starting set, so start from the widest set you
compare against.

**Filter the groups** with `where`: a calculation tests each group's works; any other field
belongs to the group itself.

```
get works where title-abstract has (kelp); then group those works by author where count of those works > (10) and h-index > (20)
get works where topic is (T10878); then group those works by institution where collaborator is not (I63966007)
```

---

## Calculate: always the last step

```
get works where country is (KE) and year >= (2015); then group those works by year; then, summarize using percent open access
get works where institution is (I63966007); then group those works by open access status; then, summarize using count, mean FWCI
get works where topic is (T10878); then, summarize using count, median citation count, sum APC paid
get works where source is (S137773608); then group those works by author; then, summarize using count, h-index
```

`count`; `mean`, `median`, `sum`, `min`, `max` of a number field; `percent` of a yes/no field;
`percent of those works` (each group's share of its set); a group's own field after a split by
those things (each author's `h-index`).

> **Sorting is not part of OQL**: it's a control in the results view (`?sort=` on the API,
> including any calculated column, e.g. `sort=mean_fwci:desc`). OQL describes *which*
> results and numbers, not how they're displayed.

---

## Limits

Up to three splits; up to 100 items in a list; at most 5 AND/OR/NOT in each listed search; a
nested split up to 10,000 groups per split (one split pages through any number); about 10
seconds a query. A query over a limit is refused before it runs, with the limit and the fix.

---

## When something's wrong, OQL tells you

OQL never guesses: a query that can't do what it looks like it does is a clear error **with a
fix**, never a silent wrong answer.

| You wrote | OQL says |
|---|---|
| `... then group those works by FWCI` | FWCI is a decimal: split it into bins, `group those works into FWCI bins at (0.5, 1, 2)` |
| `... then, summarize using authors count` | name the calculation: `summarize using mean authors count` |
| `... then group those authors by year` (after `get works`) | this query holds works: `group those works by year` |
| `title has bar*` | wildcards need quotes: `title has ("bar*")` |
| `type is (article review)` | two values need a connective: add `or` between them |
| a fourth split | a query splits its works at most three times: drop a split |

---

**Go deeper:** the **Guide** (a readable walkthrough), the **Cases** page (worked examples),
and the **Spec**, **Grammar** and **OQO schema** pages, all under `/query`.
