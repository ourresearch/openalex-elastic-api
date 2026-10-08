# The OQL guide

**OQL, the OpenAlex Query Language, lets you ask OpenAlex for works and for numbers about
them in something close to plain English.** A query is a short series of steps:

```
get works where title-abstract has ("climate change") and year >= (2020);
then group those works by year;
then, summarize using count, percent open access
```

You can read that aloud and know what it returns: climate-change papers since 2020, year by
year, with how many there are and what share is open access. That's the point: a query you
can paste into a paper's methods section, that a reader understands, and that anyone can run
again for the same answer.

## The four things to know

1. **Start with `get <things> where <conditions>`.** The things are what you get back:
   `works`, `authors`, `institutions`, `sources`, ... With no conditions, `get works` is a
   valid query.
2. **Filter fields with `is` and comparisons; search text with `has`. The value always sits
   in parentheses.** `year is (2020)`, `citation count >= (100)`, `title has (cancer)`.
3. **Add steps with `; then`.** `group those works by <field>` splits the works into groups;
   `summarize using ...` computes numbers, and is always the last step.
4. **Combine conditions with `and` / `or`; group them with parentheses.**

That's enough for most questions. Everything below is detail.

## Where to run it

- **On the search page:** the **OQL tab** at the top of the page. Valid queries run as you
  type; breakdowns show as a table.
- **On the API:** `https://api.openalex.org/?oql=<your query>`, on the API root, since the
  query names what it gets.
- **Check before you run:** `https://api.openalex.org/query/oql/<your query>` is free. It
  says whether the query is valid (and if not, what to change), how long it should take, and
  what it will cost.

Queries written the older way (`works where ... group by year`) still work, and come back in
the form above.

---

## Filtering

A condition is `<field> <operator> (<value>)`:

```
get works where type is (review)
get works where year is (2020)
get works where citation count >= (100)
get works where FWCI >= (2.0)
```

**Several values for one field** go in the same parentheses, joined with `or`, or as a set:

```
get works where type is (article or review)
get works where institution is in (I63966007, I97018004)
```

**Ranges** are two endpoint conditions: `year >= (2019) and year <= (2023)`.

**Exclude on the verb:** `type is not (review)`, `country is not (FR or DE)`,
`institution is not in (col_abc123)`.

**Entities** (institutions, authors, funders, sources, topics, ...) go in by their OpenAlex
ID. A name in square brackets after it is for reading; it's ignored on input and filled in
when the query is shown back to you:

```
get works where institution is (I136199984 [Harvard University])
```

**Codes** for closed vocabularies: `language is (en)`, `country is (US)`, `SDG is (3)`.
**Saved collections** are sets: `topic is in (col_abc123)`.

---

## Searching text

Search a text field with **`has`**: `title`, `abstract`, `title-abstract` (both at once),
`title-abstract-keywords` (title and abstract, or the keywords a phrase names), `full text`,
`raw affiliation`. The parentheses hold a portable search string, with capital `AND`, `OR`
and `NOT`, exactly as a systematic review would report it:

```
get works where title-abstract has ((asthma OR wheeze) NOT (child OR pediatric))
```

**Bare words are stemmed:** `title has (cancer)` also matches *cancers* and *cancerous*.
**Quotes mean exact:** `title has ("climate change")`, `title has ("cat")` (not *cats*).
`stemmed "genome editing"` keeps a phrase together and still stems it. **Wildcards** go in
quotes: `title has ("psoriat*")`, where `*` is any characters and `?` exactly one.
**Proximity** comes before the terms: `title has (within 3 ("smart", "phone"))`.
**Semantic search** finds works by meaning:
`title-abstract is similar to ("ocean acidification effects on coral reefs")`.

---

## Combining and nesting

Join conditions with `and` / `or` and group with parentheses. `and` binds tighter than `or`,
and the form shown back to you always adds the parentheses so nothing is left to guess:

```
get works where (year < (2000) and title-abstract has ("global warming"))
  or (title-abstract has ("climate change") and year > (2020))
```

---

## Splitting into groups

`group those works by <field>` splits the works you have into groups; everything after it is
computed within each group. Split again with `group those works again by` (up to three
splits).

```
get works where institution is (I63966007); then group those works by year
get works where institution is (I63966007); then group those works by year; then group those works again by type
```

Besides a field, you can split by:

- **listed values only:** `group those works by institution in (I63966007, I97018004, I136199984)`, one group each, in that order (up to 100);
- **searches:** `group those works by title-abstract search in (("edge AI"), ("neuromorphic computing"))`, one group per search (up to 100, at most 5 AND/OR/NOT each);
- **conditions,** to compare sets or periods: `group those works into ((institution is (I99464096)), (country is (BE)))`, or `into ((year <= (2019)), (year >= (2021)))`;
- **bins** of a number: `group those works into citation count bins at (1, 10, 100)` gives `0`, `1-9`, `10-99`, `100+`; `bins of (10)` gives equal widths. Decimals (FWCI) always need bins.

A yes/no field splits in two: `open access` and `not open access`.

**Every grouped result also has a total row** for the whole starting set, with the same
numbers and the same later splits. That's your baseline: start from the widest set you want
to compare against (the world since 2016, a country), and read the shares against the total.

**Filter the groups** by adding `where` to the split. A calculation tests each group's works;
any other field belongs to the group itself; `that <thing>` tests the group directly:

```
get works where title-abstract has (kelp);
then group those works by author where count of those works > (10) and h-index > (20)

get works where topic is in (col_abc123);
then group those works by institution where collaborator is not (I63966007)
```

Filtering on a group's own fields (h-index, last known institution) looks the groups up, so
put a count filter first; without one, a big set can take too long and the check will say so.

---

## Calculating

`summarize using` is always the last step:

```
get works where country is (KE) and year >= (2015);
then group those works by year;
then, summarize using count, percent open access
```

- `count`
- `mean`, `median`, `sum`, `min`, `max` of a number field: `mean FWCI`, `median citation count`, `sum APC paid`, `max date`
- `percent` of a yes/no field: `percent open access`, `percent retracted`
- `percent of those works`: each group's share of the set it came from
- after a split by authors, institutions or sources, their own fields: `summarize using count, h-index`

With splits you get one row per group plus the total row; without any, one row.

Sorting is **not** part of OQL: sort the table on the page, or with `?sort=` on the API (any
calculated column, `sort=mean_fwci:desc`). OQL says which works and which numbers, not how to
display them.

---

## Limits, time and price

Up to three splits; up to 100 items in a list; at most 5 AND/OR/NOT in each listed search; a
nested split up to 10,000 groups per split (a single split pages through any number); about
ten seconds a query. Anything over a limit is refused before it runs, with the limit and how
to fix it. A query with a `summarize using` step, a split by a list, bins or conditions, or a filter
on its groups is priced from what it does: the starting set costs what a list (1 credit) or a
search (10) costs, each listed search 10, each lookup 1. Nothing else adds to the price:
splits by a field, counts, means and percentages are free. Any other query costs 1 credit.
The check tells you the price for free, and a response shows what it cost in `meta.cost`.

## OQL never guesses

A query that can't do what it appears to do is always a **clear error with a fix**, never a
silent wrong answer:

```
... then group those works by FWCI       →  FWCI is a decimal: group those works into FWCI bins at (0.5, 1, 2)
... then, summarize using authors count         →  name the calculation: summarize using mean authors count
... then group those authors by year     →  this query holds works: group those works by year
title has (bar*)                         →  wildcards need quotes: title has ("bar*")
type is (article review)                 →  two values need a connective: type is (article or review)
```

---

## Going deeper

All of these live under **`/query`**:

- **Cheat sheet**: everything above on one page.
- **Cases**: worked examples, each with its OQL and the query object behind it.
- **Spec**: the formal, normative specification.
- **Grammar**: the formal grammar and a railroad diagram.
- **OQO schema**: the query object OQL compiles to, for building tools on top.

Tell us what's confusing, what's missing, and what you wish you could ask.
