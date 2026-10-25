# OQL cheat sheet

**OQL** is the OpenAlex Query Language: plain-English sentences for any OpenAlex query, from a simple search to a table of numbers. Every query starts with `get`: `get works about kelp, most cited first` or `get the count of works about kelp by country`. Try it in the **OQL tab** at the top of the search page, or call the API: `https://api.openalex.org/?oql=<your query>`. Checking a query is free: `https://api.openalex.org/query/oql/<your query>` says whether it's valid, how long it should take and what it costs, without running it, and gives it back in canonical form.

> Every example below runs on production today. Counts are live and will drift. The full
> guide, with every part: [help.openalex.org/access/oql](https://help.openalex.org/access/oql/).

## Two shapes

| Shape | Sentence | Example |
|---|---|---|
| A list of records | `get <works or things>[, <order>]` | `get works since 2023 about "large language models", most cited first` |
| A table of groups | `get the <numbers> of <works> by <splits>[, <order>]` | `get the count of works about "quantum computing" by country` |

No split is one number: `get the count of [University of Kansas](I146416000)'s works`.
After a table, `Only ...` keeps groups above a count and `Show ...` adds their own fields.

## Describe the works, in this order

| Part | Example |
|---|---|
| whose works | `[University of Kansas](I146416000)'s works`, `[Kenya](KE)'s works` |
| yes/no words | `open access`, `retracted`, `non-retracted`, `top 1% cited` |
| type | `works`, `articles`, `reviews`, `preprints`, `datasets`, `books`, `dissertations` |
| time | `since 2020`, `from 2022`, `before 2010`, `from 2018–2025` |
| search | `about kelp` (title, abstract, keywords), `with conjugal in the title` |
| citations | `citing [The state of OA: a large-scale analysis of the…](W2741809807)` |
| places | `from [Africa](Q15)`, `from both [University of Oxford](I40120149) and [University of Cambridge](I241749)` |
| venue, topic | `in [Nature](S137773608)`, `in the topic [CRISPR and Genetic Engineering](T10878)`, `in SDG [Climate action](13)` |
| money | `funded by [National Institutes of Health](F4320332161)`, `published by [Elsevier BV](P4310320990)` |
| anything else | `where language is [English](en) and citation count is at least 100` |

```
get [University of British Columbia](I141945490)'s open access articles since 2020 about kelp, most cited first
```

Entities are links: `[name](ID)`; the ID counts, the echo fills in the name.

## Search strings

Capital `AND` / `OR` / `NOT`, parentheses, **bare words stemmed, quotes exact**:

```
get works about ((asthma OR wheeze) AND child*)
get works about "climate change"
get works with (stemmed "genome editing") in the title
get works about ("smart" and "phone" within 3 words of each other)
get works where title-abstract is similar to ("ocean acidification effects on coral reefs")
```

## Conditions after `where`

```
get [Massachusetts Institute of Technology](I63966007)'s works where type is not ([review](review) or [editorial](editorial))
get [Massachusetts Institute of Technology](I63966007)'s works where citation count is at least 1000
get [Ghana](GH)'s works where it has a DOI and it doesn't have an abstract
get works where institution is [Massachusetts Institute of Technology](I63966007) or funder is [National Institutes of Health](F4320332161)
```

Numbers in words (`is above`, `is at least`, `is below`, `is at most`); negate on the verb;
several values in one pair of parentheses; yes/no fields as sentences.

## Lists of things

```
get authors at [University of British Columbia](I141945490) since 2022 with an h-index above 50
get institutions in [Austria](AT), most cited first
get journals where publisher is [Elsevier BV](P4310320990)
```

`at [X]` reads each author's own record; bare `at [X]` means any year.

## Tables of groups

- **Numbers:** `count`, `share`, `mean FWCI`, `median FWCI`, `mean citations`, `median citations`, `sum of citations`, `sum of APCs paid`, `percent open access` (any `percent <yes/no word>`).
- **Splits (one or two):** `year`, `type`, `language`, `open access`, `open access status`, `retracted`, `topic`, `subfield`, `field`, `domain`, `SDG`, `author`, `corresponding author`, `institution`, `company`, `country`, `journal`, `source`, `repository`, `publisher`, `funder`.
- **Which groups:** `by author at [X] since 2022`, `by institution in [Sweden](SE)`, `by country in ([United States](US), [China](CN))`, `by country except [Kenya](KE)`.
- **Order:** `, highest <number> first`, `, lowest <number> first`, `, fewest works first`, `, newest first`, `, alphabetical by country`, `, highest h-index first`. Default: most works first; years oldest first.

```
get the count of [University of Florida](I33213144)'s works by year since 2004
get the count and share of [France](FR)'s works by year since 2013 and open access status
get the count and mean FWCI of works about kelp by institution in [Sweden](SE), highest mean FWCI first. Only institutions with at least 10 works about kelp.
get the count of works about kelp by author at [University of British Columbia](I141945490) since 2022. Show h-index.
get the count of works from [Kenya](KE) by country except [Kenya](KE)
```

## When a sentence can't say it: the general form

`get works where <conditions>`, then steps after semicolons (`then,` each step, `finally,` the last of two or more):

```
get works where published since 2015; then, compare country [India](IN) versus country is not [India](IN) using count and mean FWCI
get works where institution is [University of Kansas](I146416000) and published in 2023; then, get each author of those works; then, get all that author's works; finally, summarize each author using mean FWCI
get works where title-abstract-keywords has (kelp); then, group those works into citation count bins at (1, 10, 100); finally, summarize using count
get works where published in 2020; then, sample 500 of those works with seed 42
```

## Defaults OQL doesn't spell out

`about` = title, abstract and keywords; the core corpus (ask for more with `get works (all corpora) where title-abstract-keywords has (kelp)`); author lists leave out authors with no works; `from [institution]` counts its sub-units; topics and journals use each work's primary topic and primary location; default orders as above.

## Limits

Two splits in a sentence (three in the general form); up to 100 values in a list; with two
splits, up to 10,000 groups per split; one walk per query; about ten seconds a query. Over a
limit, the query is refused before it runs, with how to fix it.

## When something's wrong, OQL tells you

A query that can't do what it appears to do is refused with a fix, never answered wrong:
`unknown split by FWCI` lists the splits; `, most popular first` lists the orders; `published
after 2021-06-01` asks whether you mean `since 2021-06-02` or `since 2021-06-01`; `[Harvard]`
asks for its ID; `rank ...` and `break down ...` point at `get`.
