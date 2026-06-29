# OQL cheat sheet

**OQL** is the OpenAlex Query Language — a readable way to write any OpenAlex query.
A query reads almost like a sentence: `works where title has cancer and year >= 2020`.
Try one in the **search box on a results page** (paste it in the OQL panel), or hit the
API directly: `https://api.openalex.org/?oql=<your query>`.

> Every example below runs on production today. Counts are live and will drift.

---

## The shape

```
<entity> where <conditions> [ group by <dims> ] [ sample <n> ]
```

- **entity** — what you get back: `works`, `authors`, `institutions`, `sources`, `funders`, `topics`, …
- **where** — your conditions (skip it for everything: `works`).
- A condition is `<field> <operator> <value>`: `year >= 2020`, `type is review`, `title has cancer`.

```
works
works where year is 2020
authors where last known institution is I136199984 [Harvard University]
```

---

## Filter on a field — `is`, `>=`, `<=`, `>`, `<`

| Example | Meaning |
|---|---|
| `works where year is 2020` | exact match |
| `works where type is article` | a single value, bare |
| `works where type is (article or review)` | one of several — wrap 2+ values in `( … )` |
| `works where citation count >= 100` | numeric comparison |
| `works where FWCI >= 2.0` | floats allowed |
| `works where year >= 2019 and year <= 2023` | a range = two endpoint conditions |
| `works where institution is I136199984 [Harvard University]` | entities use their OpenAlex ID; the `[name]` is optional and just for reading |
| `works where language is en` · `works where SDG is 3` | closed vocabularies use codes/ids |

The ID is what counts — anything in `[ … ]` is ignored on input and auto-filled as the
entity's name when the query is displayed back to you.

---

## Search text — `has`

Search a text field with **`has`**. Bare words are **stemmed** (so `cancer` also matches
*cancers*); **quotes** turn stemming off for an **exact** match.

| Example | Meaning |
|---|---|
| `works where title has cancer` | one stemmed word |
| `works where title has (machine learning)` | a phrase — wrap 2+ words in `( … )`; ranked by adjacency |
| `works where title has "climate change"` | **exact** phrase (no stemming) |
| `works where title has "cat"` | exact single word — excludes *cats* |
| `works where title has stemmed "genome editing"` | exact-adjacent **but** still stemmed |
| `works where title has "psoriat*"` | wildcard — **must be quoted**; `*` = any chars, `?` = one char |
| `works where title has within 3 ("smart", "phone")` | proximity — terms within N words, any order |
| `works where title/abstract is similar to "ocean acidification on coral"` | semantic (meaning-based) search |

**Text fields:** `title`, `abstract`, `title/abstract`, `full text`, `raw affiliation`, `byline`.

---

## Combine & nest — `and`, `or`, `( … )`

Join conditions with `and` / `or`. Use parentheses to group; `and` binds tighter than `or`.

```
works where title has cancer and year >= 2020
works where institution is I136199984 or funder is F4320332161
works where title/abstract has ((vape or vaping) and (health or harm))
works where (year < 2000 and title/abstract has "global warming")
  or (title/abstract has "climate change" and year > 2020)
```

---

## Exclude — `not`

Put `not` right before the value you want to exclude.

```
works where country is not FR
works where title has covid and abstract has not pediatric
works where title has (not mouse and cancer)
```

---

## Yes / no flags — `is true` / `is false`

```
works where open access is true
works where has DOI is true
works where retracted is true
```

---

## Group & sample

```
works where year >= 2020 group by topic
works where year >= 2020 group by topic, year
works where year is 2020 sample 500
```

> **Sorting and choosing columns are not part of OQL** — they're controls in the results
> view (and `?sort=` / `?select=` on the API). OQL describes *which* results, not how
> they're displayed.

---

## When something's wrong, OQL tells you

OQL never guesses — a query that can't do what it looks like it does is a clear error
**with a fix-it**, never a silent wrong answer.

| You wrote | OQL says |
|---|---|
| `title contains cancer` | `contains` was renamed → use `title has cancer` |
| `title has bar*` | wildcards need quotes → `title has "bar*"` |
| `title has climate change or warming` | wrap the terms → `title has (climate change or warming)` |
| `pub_year is 2020` | unknown field → it's `year` |

---

**Go deeper:** the **Cases** page (browsable worked examples), the **Guide** (a readable
walkthrough), and — for the truly curious — the **Spec**, **Grammar**, and **OQO schema**
pages, all under `/query`.
