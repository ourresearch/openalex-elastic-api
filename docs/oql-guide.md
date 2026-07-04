# The OQL guide

**OQL is the OpenAlex Query Language — a readable way to ask OpenAlex anything.**
Where the classic API uses URL filter strings, OQL lets you write the query out in
something close to plain English:

```
works where title has ("climate change") and year >= (2020) and open access is (true)
```

You can read that aloud and roughly know what it does — that's the whole point. OQL can
also express queries the old URL syntax never could (deep nesting, OR across different
fields, mixed exact-and-stemmed search), while compiling down to the same engine the GUI
and classic URLs already use.

## The three things to know

1. **A query is `<entity> where <conditions>`.** The entity is what you get back —
   `works`, `authors`, `institutions`, `sources`, … With no conditions, the bare entity
   is a valid query: `works`.
2. **Filter fields with `is` / `>=`; search text with `has` — the value always sits in
   parentheses.** `year is (2020)`, `citation count >= (100)`, `title has (cancer)`.
3. **Combine with `and` / `or`; group conditions with parentheses.**
   `title has (cancer) and year >= (2020)`.

That's enough to write most queries. Everything below is detail.

## Where to run it

- **On a results page:** open the OQL panel in the search box and paste a query in. This
  is the easiest way to experiment — you see results immediately and can flip between the
  point-and-click builder and the OQL text.
- **On the API:** `https://api.openalex.org/?oql=<your query>`. Note the query carries its
  own entity (`works where …`), so it goes to the API **root**, not `/works`.

---

## Filtering

A condition is `<field> <operator> (<value>)` — the value always sits in parentheses.
Most filters use `is`, or a numeric comparison:

```
works where type is (review)
works where year is (2020)
works where citation count >= (100)
works where FWCI >= (2.0)
```

**Several values for one field** — put them in the same parentheses, joined with `or`:

```
works where type is (article or review)
```

**Ranges** are just two endpoint conditions joined with `and`:

```
works where year >= (2019) and year <= (2023)
```

**Entities** (institutions, authors, funders, sources, topics, …) are referenced by their
OpenAlex ID. You can write a human label after it in square brackets to keep the query
readable — it's ignored on input and auto-filled when the query is shown back to you:

```
works where institution is (I136199984 [Harvard University])
works where institution is (I136199984) or funder is (F4320332161 [National Institutes of Health])
```

**Closed vocabularies** (countries, languages, SDGs, …) take their code or id, not their
name: `language is (en)`, `country is (US)`, `SDG is (3)`.

---

## Searching text — the heart of OQL

Search a text field with **`has`**. The fields are `title`, `abstract`, `title/abstract`
(both at once), `full text`, `raw affiliation`, and `byline`.

**Bare words are stemmed.** `title has (cancer)` also matches *cancers*, *cancerous* — the
everyday default, good recall:

```
works where title has (cancer)
works where title/abstract has (machine learning)
```

(A phrase of 2+ words is matched as a stemmed phrase, ranked higher when the words are
adjacent.)

**Quotes mean exact** — stemming off:

```
works where title has ("climate change")     ← the exact phrase
works where title has ("cat")                 ← excludes "cats"
```

**`stemmed "…"`** is the bridge: an exact-adjacent phrase that *keeps* stemming, when you
want phrase precision without losing recall:

```
works where title has (stemmed "genome editing")
```

**Wildcards** (`*` any characters, `?` one character) must be **quoted** — they run on the
exact, unstemmed text:

```
works where title has ("psoriat*")
```

**Proximity** — terms within N words of each other, in any order — is written *before* the
terms:

```
works where title has (within 3 ("smart", "phone"))
```

**Semantic search** finds works by meaning, not keywords:

```
works where title/abstract is similar to ("ocean acidification effects on coral reefs")
```

---

## Combining and nesting

Join conditions with `and` / `or`, and group with parentheses. `and` binds tighter than
`or`, so `a and b or c` means `(a and b) or c` — but the canonical form always adds the
parentheses back so nothing is left to guess:

```
works where title/abstract has ((vape or vaping) and (health or harm))

works where (year < (2000) and title/abstract has ("global warming"))
  or (title/abstract has ("climate change") and year > (2020))
```

This nesting — and OR across *different* fields
(`institution is … or funder is …`) — is what the classic URL syntax can't express.

---

## Excluding — `not`

Put `not` inside the parentheses, directly before the value to exclude:

```
works where country is (not FR)
works where title has (covid) and abstract has (not pediatric)
works where title has (not mouse and cancer)
```

There's just one way to negate — `not` before a value. To exclude a whole group, write
`(not (a or b))`.

## Yes / no flags

Boolean flags read as `is (true)` / `is (false)`:

```
works where open access is (true)
works where has DOI is (true)
works where retracted is (true)
```

## Grouping and sampling

`group by` aggregates results into buckets; `sample` returns a random subset:

```
works where year >= (2020) group by topic
works where year >= (2020) group by topic, year
works where year is (2020) sample 500
```

Sorting results and choosing which columns to show are **not** part of OQL — they're
controls in the results view (`?sort=` / `?select=` on the API). OQL says *which* works
you want, not how to display them.

---

## OQL never guesses

A query that can't do what it appears to do is always a **clear error with a fix-it** —
never a silent wrong answer. If you mistype a field, mix up syntax, or use an old keyword,
OQL tells you exactly what to change:

```
title contains (cancer)     →  "contains" was renamed; use: title has (cancer)
title has (bar*)            →  wildcards need quotes: title has ("bar*")
pub_year is (2020)          →  unknown field; it's "year"
type is (article review)    →  two values need a connective: type is (article or review)
```

---

## Going deeper

All of these live under **`/query`**:

- **Cheat sheet** — the one-page summary of everything above.
- **Cases** — a browsable library of worked examples, each with its OQL and the underlying
  query object.
- **Spec** — the formal, normative specification (every rule and edge case).
- **Grammar** — the formal grammar and a railroad diagram, for the syntax-curious.
- **OQO schema** — the canonical query object OQL compiles to, for building tools on top.

OQL is in active development and we'd love your feedback — tell us what's confusing, what's
missing, and what you wish you could express.
