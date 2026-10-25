# OQL (OpenAlex Query Language) specification

> Generated from help.openalex.org/access/oql-spec/ (openalex-help `content/access/oql-spec.md`) by
> oxjobs #1589 `work/make_upstream_guide.py`. Edit the help page, then regenerate.

> This is the **formal specification** of OQL. To get started, read the [overview](https://help.openalex.org/access/oql/) first.

OQL, the OpenAlex Query Language, is the human-readable surface over OQO, the canonical query object (see the [OQO page](https://help.openalex.org/access/oqo-schema/)). A query is an English sentence that starts with `get`:

```
get works since 2020 about kelp, most cited first
get the count of works about kelp by country
```

OQL is defined and validated in terms of OQO, not the classic URL syntax. Its bet, against Scopus, Web of Science and Dimensions, is that a researcher can **read a query aloud and understand it**.

---

## Design principles

In priority order:

1. **Reads like English.** A query is a sentence a reader understands aloud, in the order English puts things. Protect this above all.
2. **The parser carries the complexity.** Writers type something close enough; the parser reads many spellings, and the echo gives back the one canonical form. The language a reader sees stays small.
3. **Exact.** OQL maps tightly to OQO. Each word has one meaning, and the canonical text is a pure function of the OQO.
4. **Loud, never silent.** A query that can't do what it appears to do is an **error with a fix**, never a silent wrong answer.
5. **No hidden assumptions.** The text never hides a condition, value or order the query carries. The only exceptions are the [documented defaults](#documented-defaults).

## The canonical triple

```
URL  ↔  OQO  ↔  OQL          (OQO is canonical)
```

- **`OQL → OQO` is semantically lossless.** It drops only the text layer: whitespace, letter case where case carries no meaning, and the names inside links (the ID counts, the name is regenerated). It normalizes equivalent spellings to one OQO: `year >= 2020` and `since 2020` are the same query.
- **`OQO → OQL` is deterministic.** It writes the names in links, the canonical order of a sentence's parts, and the canonical spelling of every value.
- **Round-trip identity holds on the OQO side:** `OQO → OQL → OQO` is the identity. `OQL → OQO → OQL` normalizes: whatever was typed comes back in the canonical form.
- **Order inside conditions is the user's.** After `where`, the order of conditions and of values in a group is kept, not alphabetized: `where language is [English](en) and source type is [journal](journal)` and the reverse are two spellings that both echo as typed. The parts of a sentence before `where` have one canonical order instead ([the works phrase](#the-works-phrase)). Conditions on the same field gather into one clause ([merged same-field clauses](#merged-same-field-clauses)). The classic-URL and natural-language translation paths sort operands alphabetically, because their input order is machine-shaped.

This invariant is the spec's runnable contract (see [Conformance](#conformance)).

## Statement shapes

**Every statement starts with `get`, and every statement returns one of two shapes:**

| Shape | Canonical sentence | Example |
|---|---|---|
| **A list of records**: one row per work, or per thing chosen by its own fields | `get <works>[, <order>]`, `get <things>[, <order>]` | `get authors at [University of British Columbia](I141945490) since 2022 with an h-index above 50` |
| **A table of groups**: numbers about a set of works, one row per group | `get the <numbers> of <works> by <splits>[, <order>]` | `get the count of works about kelp by country` |

A table with no split is one row, the smallest table: `get the count of [University of Kansas](I146416000)'s works`. Two short sentences can follow a table: `Show ...` adds the groups' own fields, and `Only ...` keeps the groups by a count of their works:

```
get the count and mean FWCI of works about kelp by institution in [Sweden](SE), highest mean FWCI first. Only institutions with at least 10 works about kelp.
```

The order is always the words after the last comma, so changing the order never changes the rest of the sentence.

### Sentences and the general form

OQL has two ways to write a statement:

- **The sentence form** ([below](#the-sentence-grammar)) says lists, and tables of groups with up to two splits.
- **[The general form](#the-general-form)** says the rest: it starts `get works where <conditions>` and adds steps after semicolons.

**The echo uses a sentence whenever one can say the query, and the general form only when none can.** Both are fully supported. Today the echo falls back to the general form for:

- comparing one thing against the rest, or conditions, searches or periods side by side (`compare country [India](IN) versus country is not [India](IN)`); named things side by side are a table (`by country in ([United States](US), [China](CN))`);
- walks (each author of a set, then all their works);
- number bins, samples, and three splits;
- splits by continent, institution type, source type, license, keyword or global south, and by corresponding institution;
- numbers outside the sentence's list (`mean reference count`, `min date`, `percent global south`), and counts of distinct things (`summarize all those authors using count`);
- a filter on the groups by a number other than the count (`where mean FWCI of those works is at least 2`);
- groups chosen by own fields a split can't say (`last known institution`, `co-author is not`, `institution type`);
- a corpus other than the core (`(all corpora)`).

```
get works where published since 2015; then, compare country [India](IN) versus country is not [India](IN) using count and mean FWCI
```

The general form has no order phrase. Its results come back in the default order.

## The sentence grammar

### Lists

```
get <works phrase>[, <order>]
get <things phrase>[, <order>]
```

A list of works returns one row per work. A list of things returns authors, institutions, journals and other things chosen by their own fields: what is on their own record, not counts of some works.

### Tables of groups

```
get the <numbers> <of|to|for> <works phrase> by <split>[ and <split>][, <order>][. Show <own fields>.][ Only <things> with <count> <works phrase>.]
get the <numbers> <of|to|for> <works phrase>
```

A table takes a set of works, splits it into groups, and gives numbers for each group. With two splits there is one row per pair. A table has five parts, each with its own words: the works ([works phrase](#the-works-phrase)), the [splits](#splits), [which groups](#which-groups) to keep, the [numbers](#numbers), and the [order](#orders).

The word before the works phrase depends on the last number: `to` after `sum of citations`, `for` after `sum of APCs paid`, `of` otherwise.

```
get the sum of citations to works about kelp by year
get the sum of APCs paid for works about kelp by publisher
```

### The works phrase

Lists and tables describe their works with the same words. The parts go in this order, and the echo puts them back in it whatever order they were typed in:

| # | Part | Canonical words |
|---|---|---|
| 1 | Whose works | `[University of Kansas](I146416000)'s works`: one institution, country or author that defines the set |
| 2 | Yes/no words | `open access`, `closed access`, `retracted`, `non-retracted`, `top 1% cited`, `top 10% cited` |
| 3 | The type | `works`, `articles`, `reviews`, `preprints`, `books`, `book chapters`, `datasets`, `conference papers`, `dissertations`, `editorials`, `letters`, `reports`; `all works` in a table when nothing else narrows them |
| 4 | Time | `since 2020`, `from 2022`, `before 2010`, `through 2010`, `from 2018–2025`; dates `since 2021-06-01`, `through 2021-09-30`, `from 2020-10-01 through 2021-09-30` |
| 5 | Searches | `about kelp`; `with kelp in the title`, `in the abstract`, `in the full text`, `in the title or abstract` |
| 6 | Citations | `citing [W](W2741809807)`, `cited by [W](W2741809807)`, `citing works in the collection [C](col_8yWKmRNyEr)` |
| 7 | Places | `from [Kenya](KE)`, `from [Africa](Q15)`, `from A or B`, `from both A and B`, `from all of A, B, and C`; `co-authored with [institution]` |
| 8 | People | `by [Jason R Priem](A5023888391)`, `co-authored by A and B`, `with [A](A5023888391) as corresponding author` |
| 9 | Where the work sits | `in [Nature](S137773608)`, `in SDG [Climate action](13)`, `in the topic [..](T10878)`, `in the subfield`, `in the field`, `in the domain`, `in the collection [C](col_8yWKmRNyEr)` |
| 10 | Publisher, funder, license | `published by [Elsevier BV](P4310320990)`, `funded by A or B`, `under the [CC-BY](cc-by) license` |
| 11 | Anything else | `where <conditions>` ([Conditions](#conditions)) |

All together:

```
get [University of British Columbia](I141945490)'s open access articles since 2020 about kelp, most cited first
```

Rules the echo follows:

- **The possessive.** When exactly one institution, country or author narrows the works, it becomes the possessive: `where country is GB` echoes `get [United Kingdom](GB)'s works`. With two (an institution and an author), neither is: `get works from [Massachusetts Institute of Technology](I63966007) by [Jason R Priem](A5023888391)`. A table split by institution, country or author never uses the possessive.
- **`co-authored with`** replaces `from` for an institution when the table splits by institution: `get the count of works since 2015 co-authored with [Christian-Albrechts-Universität zu Kiel](I32021983) by company`.
- **Time.** Years are whole years: `year > 2019` echoes `since 2020`; a closed range uses an en dash (`from 2018–2025`). Full dates appear only when the query carries them. In a table split by year, the time follows `by year` instead (`by year since 2000`).
- **Searches** go in the order about, title, abstract, full text, title or abstract.
- **Kinds.** `in [X]` alone means a source (a journal or repository). Every other value whose kind isn't obvious names it: `SDG`, `the topic`, `the subfield`, `the field`, `the domain`, `the collection`, `the ... license`. A role other than an entity's default names its key (`with [A](A5023888391) as corresponding author`).
- **Lists of values.** Several institutions, countries, sources or funders that any work may match read `A or B`. Works that must match all of several places read `from both A and B` or `from all of A, B, and C`.
- **Work titles** in `citing` and `cited by` are cut at a word boundary within 48 characters, with an ellipsis: `get works citing [The state of OA: a large-scale analysis of the…](W2741809807)`. The ID is what counts.
- **`where`** holds only what the phrase can't say: an `or` across fields, nested groups, negations, and fields with no phrase. The easy parts stay in the phrase.

### The things phrase

```
get <things>[ <parts>][ <own thresholds>][ where <own-field conditions>][, <order>]
```

**Things:** `authors`, `institutions`, `companies`, `countries`, `sources`, `journals`, `repositories`, `publishers`, `funders`, `topics`, `fields`, `subfields`.

| Part | Canonical words | Example |
|---|---|---|
| An author's own record | `at [institution]`, `in [country]`, each with an optional `in 2+ years` and a time | `get authors at [University of British Columbia](I141945490) in 2+ years since 2020` |
| Never on the record | `never at [institution]`, `never in [country]` | `get authors never at [University of British Columbia](I141945490) where last known institution is [University of Washington](I201448701)` |
| A thing's own place | `in [country]`, `in [continent]` (not for authors) | `get institutions in [Africa](Q15)` |
| A classification | `in the field [X]`, `in the subfield [X]`, `in the domain [X]` | `get topics in the field [Computer Science](17)` |
| Leaving some out | `except [X]`, `except ([A], [B])` | `get institutions in [Germany](DE) except [Max Planck Society](I149899117)` |
| Own numbers | `with an h-index`, `an i10-index`, `a works count`, `a citation count`, then `above`, `at least`, `below` or `at most`, then a number | `get authors with a works count above 1000` |
| Any other own field | `where <conditions>` | `get institutions where city is Vienna` |

`at [X]` reads each author's own record (the institutions on their profile, with years), not the papers' affiliations. Bare `at [X]` means any year; a window is written out (`at [X] since 2022`). OpenAlex's best guess at where an author is now is the field `last known institution`.

### Numbers

Numbers are joined with `and`, with an Oxford comma for three or more. A number covers the matching works in each group.

| Number | Meaning |
|---|---|
| `count` | how many works |
| `share` | each row's slice of the group one level up: of the whole set with one split; of each year with `by year and country` |
| `sum of citations`, `sum of APCs paid` | totals over the works |
| `mean FWCI`, `median FWCI`, `mean citations`, `median citations` | averages over the works |
| `percent <yes/no word>` | the rate within each row: `percent open access`, `percent retracted`, `percent top 1% cited`, `percent top 10% cited`, `percent with an abstract`, `percent with full text`, `percent with a DOI` |

```
get the percent open access, percent retracted, percent with an abstract, percent with full text, percent with a DOI, percent top 1% cited, and percent top 10% cited of works about kelp by year
```

A thing's own fields (`h-index`, `works count`) are not numbers about the works: they go in a [`Show` sentence](#show). `share` and the own fields need a split.

### Splits

One or two splits, joined with `and`, never the same split twice:

- **Fields of the works:** `year`, `type`, `language`, `open access`, `open access status`, `retracted`, `topic`, `subfield`, `field`, `domain`, `SDG`.
- **Things:** `author`, `corresponding author`, `institution`, `company`, `country`, `journal`, `source`, `repository`, `publisher`, `funder`.

```
get the count of works about kelp by year since 2000
get the count of works about kelp by field and year
```

A yes/no split gives two groups (`open access` and `not open access`). `topic`, `subfield`, `field` and `domain` use each work's primary topic; `journal` and `source` use its primary location. Every other split is said in [the general form](#the-general-form).

### Which groups

Which groups is not which works. Words right after a split word choose the groups; the works phrase chooses the works.

| Words after the split | Groups | Example |
|---|---|---|
| `in (<value>, ...)` | just these, in this order, up to 100 | `get the count of works about kelp by type in ([article](article), [review](review))` |
| `in the collection [C]` | the members of a [collection](#collections) | `get the count of works about kelp by country in the collection [European Union (EU27)](col_LV29j8URoX)` |
| `at [institution]`, `in [country]` (authors) | people whose own record has it | `get the count of works about kelp by author at [University of British Columbia](I141945490) since 2022` |
| `in [country]`, `in [continent]` | the things' own country or continent | `get the count of works about kelp by institution in [Canada](CA)` |
| `with an h-index above 40` | an own number | `get the count of works about kelp by author with an h-index above 40` |
| `except [X]`, `except ([A], [B])` | everyone but these | `get the count of works about kelp by country except [Norway](NO)` |

A list of journals echoes as `by source in (...)`. `by author at [X]` keeps the people whose record has X and counts all their matching works, wherever they wrote them; `from [X] by author` keeps the works with an X author and counts everyone on them:

```
get the count of works about kelp by author at [University of British Columbia](I141945490) since 2022
get the count of works about kelp from [University of British Columbia](I141945490) by author
```

### Only

`Only` keeps the groups with enough of the same works, as its own sentence after the table:

```
get the count of works about kelp by author. Only authors with at least 20 works about kelp.
```

- The words: `Only <things> with <more than | at least | fewer than | at most> <N> <works phrase>.`
- `<things>` is the plural of a split by things in the table.
- The works phrase is the table's own; the echo writes it out in full (`Only authors with at least 20 works.` echoes with `about kelp`). A count over other works is refused.
- A threshold on an own field folds into the split: `Only authors with an h-index above 50.` echoes as `by author with an h-index above 50`.

### Show

`Show` adds a thing's own fields as columns: `Show h-index.`, `Show works count.`, `Show h-index and works count.` It needs a split by things that have the field. An order by an own field shows it without `Show`:

```
get the count of works about kelp by author, highest h-index first. Show works count.
```

When a table has both, `Show` comes before `Only`.

### Orders

The order is the words after the last comma. The echo leaves out a default order.

**Lists of works:**

| Order | Sorts by |
|---|---|
| `, most cited first` / `, least cited first` | citation count |
| `, newest first` / `, oldest first` | publication date |
| `, highest FWCI first` / `, lowest FWCI first` | field-weighted citation impact |
| `, alphabetical by title` / `, reverse alphabetical by title` | title |
| `, best matches first` | relevance; needs a search; the default when there is one |
| `, most cited (age-adjusted) first` | citations for their year; the default without a search, so written only with one |

Any other sortable field has words by its kind: a number `, highest reference count first` / `, lowest ... first`; a date `, latest updated date first` / `, earliest ... first`; a yes/no field `, open access first` / `, open access last`; text or a code `, alphabetical by type` / `, reverse alphabetical by type`; an ID `, in source ID order` / `, in reverse source ID order`.

```
get works about kelp, most cited (age-adjusted) first
get works since 2020, highest reference count first
```

**Lists of things:** `, highest h-index first`, `, lowest h-index first`, `, highest i10-index first`, `, lowest i10-index first`, `, most cited first`, `, least cited first`, `, lowest works count first`. The default is most works first.

```
get authors with an h-index above 50, lowest i10-index first
```

**Tables:**

| Order | Sorts by |
|---|---|
| `, highest <number> first` / `, lowest <number> first` | any number in the table (`, highest mean FWCI first`, `, highest share first`); with one number, `, highest first` |
| `, most works first` / `, fewest works first` | count |
| `, newest first` / `, oldest first` | years, when the first split is year |
| `, alphabetical by <split>` / `, reverse alphabetical by <split>` | the group's name, for a split by text, a code or a yes/no field |
| `, in <split> ID order` | the group's ID, for a split by things |
| `, highest h-index first` / `, lowest ... first` | a thing's own field (`h-index`, `i10-index`, `works count`, `citation count`); shows it |

```
get the count of works about kelp by country, fewest works first
get the count of works about kelp by year, newest first
```

An order sorts every group, not just the first page, and orders two splits as one flat table. With no order, a table comes back most works first, and a table whose first split is year comes back oldest first.

## Conditions

Conditions follow `where`: at the end of a works phrase, in a things phrase, in [the general form](#the-general-form), and inside [sets](#sets). They join with `and` and `or`, and group with parentheses:

```
get works where institution is [Harvard University](I136199984) or funder is [National Institutes of Health](F4320332161)
```

A clause is a field, a verb, and a value. The verbs:

| Verb | Clause |
|---|---|
| `is`, `is not` | a value or a group of values: `type is not [review](review)` |
| `is above`, `is at least`, `is below`, `is at most` | a number: `citation count is at least 100` |
| `has` | a [search](#search): `title has kelp` |
| `is similar to` | a semantic search: `title-abstract is similar to ("...")` |
| `published since`, `before`, `after`, `in`, `through` | a year or date: `published before 2000` |
| `it's`, `it has`, `it doesn't have` | a [yes/no field](#yesno-fields): `it has a DOI` |
| `is in the collection`, `is not in the collection` | a [collection](#collections) |
| `is in the set`, `is not in the set` | a [set](#sets) |
| `it cites`, `it's cited by`, `it's related to` | the work's [relations](#relations) |

A condition the works phrase can say moves into the phrase: `where year >= 2020` echoes `since 2020`, `where type is article` echoes `articles`, `where it's open access` echoes `open access works`.

### Entity references

An entity is a link: the name in brackets, the ID in parentheses.

```
get works where institution is [Harvard University](I136199984) or funder is [National Institutes of Health](F4320332161)
```

- **The ID is what counts.** The name is ignored on input and regenerated on output, so it can't lie: `[those Harvard folks](I136199984)` echoes `[Harvard University](I136199984)`. On input the name may be left out (`(I136199984)` in a sentence, a bare `I136199984` after `where`).
- **A name with no ID is an error:** `institution is [Harvard]` is refused with the fix `[Harvard University](I136199984)`. The parser never looks names up.
- **IDs are bare:** `I136199984`, `KE`, `Q15`, `col_LV29j8URoX`, no `https://openalex.org/` prefix needed.
- **Closed vocabularies are links too**, with their code as the ID: `[article](article)`, `[English](en)`, `[gold](gold)`, `[journal](journal)`. Countries use their two-letter code (`[Kenya](KE)`), continents their Wikidata ID (`[Africa](Q15)`), fields, subfields, domains and SDGs their number (`[Computer Science](17)`).
- **Value case is cosmetic.** Matching ignores case. The echo writes country codes in capitals (`KE`), vocabulary codes in lowercase (`article`), and IDs and search text as given.

### Value groups

One value needs no parentheses. Several values share one pair, joined with `or` or `and`:

```
get works where type is ([article](article) or [review](review))
get works where institution type is ([company](company) and [government](government))
```

- **Inside a group, the join is always written.** `type is (article review)` is refused: add `or` between the values (or `and` if you mean both). Commas are refused too.
- **Two or more values need parentheses.** `type is article review` is refused.
- **`or`** matches any value; **`and`** matches works with all of them (for a field with one value per work, like `type`, that is no works, which is coherent, not an error).
- **Groups nest:** `institution type is (([company](company) or [government](government)) and not [education](education))`.
- **A comparison, a yes/no value, a collection and a semantic passage take exactly one value.** `year >= (2019 or 2020)` is refused; `citation count is (100 or 200)` is fine (`is` on a number is an ordinary set).
- **`unknown`** in a group is the empty value: `language is ([English](en) or unknown)`.

### Merged same-field clauses

Conditions on one field gather into one clause, with the boolean structure inside the parentheses:

```
get works where funder is ([National Institutes of Health](F4320332161) and not [Wellcome Trust](F4320311904)) or type is [review](review)
get works with (kelp NOT urchin) in the title
```

- Affirmed values gather into `is (A or B)` or `is (A and B)`. Negated values joined by `and` move the negation to the verb: `institution is not ([University of Florida](I33213144) or [Stanford University](I97018004))`. Any other group writes `not` before each negated value.
- Search conditions on one place gather into one search string.
- Comparisons stay separate clauses (`citation count is above 100 and citation count is below 1000`), as do collections, sets and semantic searches.
- This is a rule about the text only: the OQO keeps one leaf per value.

### Numbers and years

A number field takes `is above`, `is at least`, `is below` or `is at most`, one clause per bound:

```
get works where citation count is above 100 and citation count is below 1000
get works where FWCI is at least 1.5 and FWCI is at most 3
```

- **Bounds stay as written.** `year is above 42 and year is below 100` is not rewritten to inclusive bounds.
- **Four-digit years are whole years.** In a works phrase they read as time words: `year >= 2019 and year <= 2023` echoes `from 2019–2023`, and `year > 2019` echoes `since 2020`. Inside a `where` that the phrase can't absorb, they read `published since 2015`, `published before 2000`, `published after 2020`, `published in 2015`, and dates the same way (`published since 2021-06-01`).
- **There is no dash-range value.** `year is 2019-2023` is refused with the fix `year >= 2019 and year <= 2023`. (The classic URL form `publication_year:2019-2023` still works on URLs.)
- **`after` a date is ambiguous** (does it include the day?) and is refused: write `published since 2021-06-02`, or `since 2021-06-01` to include it. `after` a year means the next year on.
- **Numbers of 10,000 or more** take thousands commas in a things phrase (`with a citation count above 100,000`).

### Booleans and precedence

```
get works where type is [article](article) or (type is [review](review) and language is [English](en))
```

- **`and` binds tighter than `or`**, and `not` binds tightest (`NOT > AND > OR`), the order of boolean algebra and of Web of Science and Scopus. A mix of `and` and `or` at one level is not an error.
- **The echo always writes the parentheses**, so the grouping is never left to the reader.
- **Two conditions with no `and` or `or` between them** are refused.
- Between conditions and inside value groups, `and`, `or` and `not` are lowercase. Inside a search string, `AND`, `OR` and `NOT` are capitals ([Search](#search)).

### Negation

Negation goes on the verb:

```
get works where type is not ([review](review) or [editorial](editorial))
```

- **One negated value, or negated values joined by `and`:** `is not [X]`, `is not ([A] or [B])` (works with none of them).
- **Any other group** writes `not` before each negated value: `funder is ([National Institutes of Health](F4320332161) and not [Wellcome Trust](F4320311904))`, `type is (not [article](article) or not [review](review))`.
- **Yes/no fields negate by their word:** `closed access`, `non-retracted`, `it doesn't have an abstract`, `it's not retracted`.
- **Searches negate with `NOT`** inside the search string: `(kelp NOT urchin)`.
- **An author's record negates with `never`:** `never at [X]`, `never in [X]`.
- **Collections and sets negate on the verb:** `is not in the collection`, `is not in the set`, `it doesn't cite any work in the set`.

### Search

**`has` searches; bare words are stemmed and quotes mean exact.**

| Search string | Meaning |
|---|---|
| `cat` | one word, stemmed: also matches *cats* |
| `"cat"` | exact: no stemming |
| `(climate change OR warming)` | a run of bare words is one stemmed search node, ranked higher when the words are adjacent; `OR` joins two nodes |
| `"climate change"` | the exact, adjacent phrase |
| `(stemmed "whopper junior")` | an adjacent phrase that keeps stemming (matches *whoppers junior*) |
| `"rock or roll"` | inside quotes, `or` is a word: one exact phrase |
| `((climate AND change) OR warming)` | `AND` binds tighter than `OR`; the echo writes the parentheses |
| `(kelp NOT urchin)` | `NOT` leaves works out |
| `(road traffic "and" ghana)` | a quoted operator word is a literal word |

```
get works with (climate change OR warming) in the title
get works with "climate change" in the title
get works where title has kelp or abstract has urchin
```

- **The search string is portable**, as a systematic review would report it: capital `AND`, `OR` and `NOT`, parentheses for grouping. One word or one quoted phrase needs no parentheses; anything more does. Lowercase `and`, `or`, `not` and `&` work in a search string, and the echo writes capitals.
- **Two or more bare words need parentheses or quotes** after `has`: `title has climate change` is refused, because a reserved word could otherwise be swallowed silently.
- **Places:** `about` searches the title, the abstract and the keywords. A `with ... in the ...` phrase searches one place: `the title`, `the abstract`, `the full text` (title, abstract and full text), `the title or abstract`. After `where`, searches name their field: `title has`, `abstract has`, `title-abstract has`, `title-abstract-keywords has`, `full text has`, `raw affiliation has`, `byline has`.
- **On `raw affiliation` and `byline`**, a quoted phrase and a proximity window each stay within one affiliation or one byline.
- **Semantic search:** `title-abstract is similar to ("ocean acidification effects on coral reefs")` searches by meaning and returns the 50 closest works. It takes exactly one quoted passage. `title` and `abstract` take it too.
- **OQL never adds words.** No synonyms, no expansions: the search is exactly the string.
- **No other search syntax leaks through.** `~` (fuzzy matching or slop), `|` (the URL's OR) and `\` (an escape) are refused with a fix, never passed to the engine. Fuzzy matching is not in OQL yet.

The openalex.org search box treats quotes differently: there a quoted phrase stays stemmed. The translator keeps the meaning: the URL `title_and_abstract.search:"climate models"` echoes `get works with (stemmed "climate models") in the title or abstract`.

### Proximity and wildcards

**Proximity** finds two or more terms within N words of each other, in any order:

```
get works with ("smart" and "phone" within 3 words of each other) in the title
get works with (smart and phone within 3 words of each other) in the title
get works with ("machine learning" and "neural network" within 5 words of each other) in the title
get works where raw affiliation has (london and hospital within 5 words of each other)
```

- Three or more terms list with an Oxford comma: `("foo", "bar", and "baz" within 3 words of each other)`.
- Terms are all bare (stemmed) or all quoted (exact). A mix is refused. A quoted term may be a phrase.
- Proximity needs at least two terms.

**Wildcards:** `*` matches any characters and `?` exactly one. A term with a wildcard runs on exact (unstemmed) text, so it matches the word forms as written:

```
get works with bar* in the title
get works with wom?n in the title
get works with "smart* phone" in the title
get works with ("smart*" and "phone" within 3 words of each other) in the title
```

- A wildcard may sit inside a word (`foo*bar`) or a quoted phrase (`"smart* phone"`).
- A wildcard may not start a word (`*cycle` is refused), and `*` needs at least 3 characters before it (`ab*` is refused).
- In a proximity, a wildcard term must be quoted (and so all its terms are quoted).
- `stemmed` and a wildcard contradict each other and are refused.

### Null and unknown

`unknown` is the empty value:

```
get works where language is unknown
get works where language is not unknown
get works where language is ([English](en) or unknown)
get works from 2024 about kelp where institution is unknown
```

### Yes/no fields

Yes/no fields read as words about the work. In the works phrase, the adjectives come before the type: `open access`, `closed access`, `retracted`, `non-retracted`, `top 1% cited`, `top 10% cited`.

```
get open access retracted articles
get [Ghana](GH)'s works where it has a DOI and it doesn't have an abstract
get works where type is ([article](article) or [review](review)) and (it's open access or it's retracted)
```

After `where`, the sentences are `it's open access`, `it's retracted`, `it's in the top 1% by citations`, `it's in the top 10% by citations`, `it's from the global south` (each with `it's not`), and `it has a DOI`, `it has an ORCID`, `it has an abstract`, `it has full text` (each with `it doesn't have`). A yes/no field takes exactly one value. A sentence the works phrase can say moves into it: `where it's open access` echoes `open access works`.

### Collections

A [collection](https://help.openalex.org/how-to/collections/) is a saved set of entities, addressed by a `col_...` ID, written as a link:

```
get works in the collection [Example: altmetrics papers](col_8yWKmRNyEr)
get works where work is not in the collection [Example: altmetrics papers](col_8yWKmRNyEr)
get works from 2024 about kelp where country is not in the collection [European Union (EU27)](col_LV29j8URoX)
```

- **What a collection means depends on what it holds.** `works in the collection [X]` is the works in a works collection, or the works from the members of a collection of countries, institutions or people.
- **`citing works in the collection [X]`** is the works citing any work in a works collection.
- **In a table**, `by country in the collection [X]` gives one row per member ([which groups](#which-groups)).
- **One collection per clause.** Join several with `or` clauses.
- **In a sentence, write the collection's ID as a link** (`[name](col_...)`, or `(col_...)` with the name left out); a bare `col_...` is an error.

### Sets

A set is a query inside a condition, written as a phrase with no `get` that names what it holds:

```
get works since 2025 where author is in the set (authors of works where title-abstract has kelp and published since 2022)
get works about kelp where author is in the set (authors where last known institution is [University of Kansas](I146416000))
get works where institution is in the set (institutions where country is [Kenya](KE))
```

- The phrase is `works where ...`, `authors of works where ...`, or `<things> where <their own fields>`.
- **The set must hold what the field takes.** `author is in the set (works ...)` is refused: an author field takes authors.
- **A set holds up to 450,000 IDs**, to stay inside about ten seconds; a bigger one is refused, with the fix to narrow it or save it as a collection.

### Relations

A work's citations read as verbs. In the works phrase: `citing [W]`, `cited by [W]`, `citing works in the collection [C]`. After `where`, a set or a related work:

```
get works citing [The state of OA: a large-scale analysis of the…](W2741809807)
get works cited by [The state of OA: a large-scale analysis of the…](W2741809807)
get works where it's related to ([The state of OA: a large-scale analysis of the prevalence and impact of Open Access articles](W2741809807))
get the count of works where it cites a work in the set (works where institution is [University of Kansas](I146416000)) by year
get works from 2024 in the topic [CRISPR and Genetic Engineering](T10878) where it doesn't cite any work in the set (works where institution is [University of Kansas](I146416000))
get works since 2020 where it isn't cited by any work in the set (works where institution is [University of Kansas](I146416000) and published in 2023)
```

The set forms: `it cites a work in the set (...)`, `it doesn't cite any work in the set (...)`, `it's cited by a work in the set (...)`, `it isn't cited by any work in the set (...)`, `it's related to a work in the set (...)`, `it isn't related to any work in the set (...)`. To leave out works citing one paper, use the set form.

### Delimiters

| Delimiter | Meaning |
|---|---|
| `[ … ]( … )` | a link: a name (ignored on input) and an ID |
| `( … )` | a group of conditions, a group of values, a search group, a list of values or a set |
| `" … "` | an exact phrase |
| `,` | before the order; between listed values, bins and proximity terms |
| `.` | ends a table's main sentence before `Show` or `Only`, and ends each of those |
| `;` | between the general form's steps |
| `{ … }` | unused |

**OQL has no escape sequences.** Two lexing rules make this work: strings are scanned whole (any delimiter inside `" … "` is inert), and a link's name runs to the first `]`. Only `"` delimits strings, so apostrophes are ordinary characters (`"parkinson's disease"`).

## The general form

The general form says what no sentence can. It starts with `get` and the works or things it is about, and adds steps after semicolons: `then,` before each step, and `finally,` before the last of two or more.

```
get works where <conditions>[; then, <step>]*[; finally, <step>]
```

### Starts

- **Works:** `get works where <conditions>`. A corpus other than the core is written after the noun: `get works (all corpora) where title-abstract-keywords has (kelp)`, or `(expansion corpus)`.
- **Things that did something:** `get <things>[ where <their own fields>] <verb> works where <conditions>`, one row per thing. The verbs: `who published` (authors), `that published` (institutions, sources, publishers, countries), `that funded` (funders), `of` (topics), and the roles `who were corresponding authors of`, `that were corresponding institutions of`. A count may precede `works`: `who published more than 5 works where ...`.

```
get authors where last known institution is [University of Kansas](I146416000) who published works where title-abstract-keywords has (kelp); then, summarize each author using count
get institutions that were corresponding institutions of works where title-abstract-keywords has (kelp); then, summarize each institution using count
```

### Splits and bins

```
then, group those works by <split>[ and <split>][ where <group filter>]
then, group those works into <number field> bins at (<edge>, <edge>, ...)
then, group those works into <number field> bins of <width>
```

- **Up to three splits, in one step:** `by continent and year`; three with an Oxford comma, `by continent, institution type, and year`. A split next to bins, or after a group filter, takes its own `by`: `into citation count bins at (1, 10, 100) and by year`, `by year and by citation count bins at (1, 10, 100)`.
- **Any field splits**, including the ones a sentence can't (`continent`, `institution type`, `source type`, `license`, `keyword`, `global south`). A decimal field can't split by value: it needs bins.
- **Bins** at edges `(1, 10, 100)` give `0`, `1-9`, `10-99` and `100+`; `bins of 0.5` gives equal widths.
- **A group filter** after `where` keeps the groups by a number about their works (`mean FWCI of those works is at least 2`, `count of those works is above 5`) or by their own fields.

```
get works where title-abstract-keywords has (kelp); then, group those works by continent, institution type, and year; finally, summarize using count
get works where title-abstract-keywords has (kelp); then, group those works into citation count bins at (1, 10, 100); finally, summarize using count
get works where title-abstract-keywords has (kelp); then, group those works by year and by citation count bins at (1, 10, 100); finally, summarize using count
get works where title-abstract-keywords has (kelp); then, group those works by author where mean FWCI of those works is at least 2 and count of those works is above 5; finally, summarize using count and mean FWCI
```

### Compare

`compare` puts conditions, searches or periods side by side, one group each, with its numbers and optional splits:

```
then, compare <condition> versus <condition>[ versus ...][ using <measures>][ by <split>]
```

```
get works where title-abstract-keywords has (kelp); then, compare published before 2015 versus published since 2015 using count and mean FWCI
get works where title-abstract-keywords has (kelp); then, compare open access versus type [article](article) using count by year
get works where title-abstract-keywords has (kelp); then, compare title-abstract has salmon versus (urchin OR otter) using count
```

- Each item is a condition. A yes/no field alone means true (`open access`); `is` may go unsaid before a value (`country [India](IN)`); a later item may drop the field it shares with the one before.
- A comparison comes before any other split; further splits follow `by`.
- Named things side by side are a table, and echo as one: `compare country [Norway](NO) versus [Canada](CA) using count by year` echoes `by country in ([Norway](NO), [Canada](CA)) and year`.

### Summaries

```
then, summarize[ each <thing> | all those <works or things>] using <measure>[, <measure>]*
```

The summary is always the last step. Its measures:

| Measure | Meaning |
|---|---|
| `count` | how many |
| `mean`, `median`, `sum`, `min`, `max` + a number field | over the works: `mean reference count`, `sum citation count`; `min` and `max` also of a date (`min date`) |
| `percent` + a yes/no field | the rate: `percent open access`, `percent global south` |
| `percent of those works` | each group's slice of its parent set |
| a thing's own field | after a split by things: `h-index` |

A bare field is not a measure: `summarize using authors count` is refused with the fix `mean authors count`.

```
get works where title-abstract-keywords has (kelp); then, group those works by continent; finally, summarize using median FWCI, max citation count, min date, and percent open access
get works where author is [Jason R Priem](A5023888391); then, summarize all those works using min date and max date
get authors who published works where topic is [CRISPR and Genetic Engineering](T10878); then, summarize all those authors using count
```

The last counts distinct authors.

### Samples

```
get works where published in 2020; then, sample 500 of those works with seed 42
```

A sample with a seed is the same sample every time.

### Walks

A walk goes from the works to the things related to them (`then, get each author of those works`, one result per author; `then, get authors of those works`, one combined set), then back to everything those things did (`then, get all that author's works`, `then, get all those authors' works`):

```
get works where institution is [University of Kansas](I146416000) and published in 2023; then, get each author of those works; then, get all that author's works; finally, summarize each author using mean FWCI
get works where institution is [University of Kansas](I146416000) and published in 2023; then, get authors of those works; then, get all those authors' works; finally, summarize all those works using count
```

The first is each Kansas 2023 author and the mean FWCI of all their works. One walk out and one walk back per query, before any split. A walk out starts from works; a walk from authors on to institutions is refused, with the fix to walk back to their works first.

### Results

A table has one row per group, with a column for each split and each number, plus a **summary** (`summary` in the JSON): the whole starting set (`summary.all`) and, with two or more splits, each split's groups on their own over the whole set (`summary.splits[i].groups`, in the order of `meta.splits`). Summary numbers are computed from the works, never from the group rows.

### Limits and time

The free check (`GET /query/oql/<query>`) applies every limit before anything runs, and gives the fix for each one: two splits in a sentence and three in the general form; 100 values in a list; with two splits, 10,000 groups per split (one split pages through any number); one walk out per query; a set of up to 450,000 IDs; about ten seconds a query (a query estimated over that is refused).

## Documented defaults

OQL's text never hides a condition the query carries, with these exceptions: sensible defaults it doesn't spell out.

| Default | What it means |
|---|---|
| `about` | searches the title, the abstract and the keywords |
| The core corpus | every query runs on OpenAlex's core corpus; the general form's `(all corpora)` or `(expansion corpus)`, or `include_xpac=true` on the API, adds the rest |
| Authors with works | lists of authors leave out authors with no works |
| Sub-units count | `from [institution]` and `[institution]'s works` include its sub-units (a university's hospitals and institutes) |
| Primary topic | `in the topic / subfield / field / domain` and splits by them use each work's primary topic, not every topic it has |
| Primary location | `in [journal]` and `by journal` / `by source` use each work's primary location |
| Default orders | a list with a search: best matches first; a list without: most cited (age-adjusted) first; things: most works first; a table: most works first, years oldest first |

Nothing joins this list silently: every default is documented wherever OQL is documented.

## Diagnostics

**A query that can't do what it appears to do is refused before it runs, and the error says how to fix it.** Every error has a `type` (`parse_error`, `invalid_value`, `invalid_measure`, `query_too_slow`, ...) and a `message` that ends with the fix after `  Fix: `. The execute surface also gives the `position` and a `context` snippet when it knows them. The free check endpoint returns the same errors at no cost.

**Sentences:**

| You wrote | OQL says |
|---|---|
| `by FWCI` | unknown split; lists the splits a table takes |
| `the authors count of works ...` | unknown numbers; lists the numbers |
| `, most popular first` | unknown order; lists the orders a list takes |
| `by year and country and type` | three splits; a table splits two ways at most |
| `by year and year` | the same split twice |
| `, highest first` with two numbers | `highest first` with more than one number: name it |
| `the share of works about kelp` (no split) | share needs a split |
| `Show h-index` with no split by things | `h-index` needs a split by things that have it |
| `Only ...` after a list | an `Only` sentence follows a table |
| `Only authors ...` on a table split by country | names things the table doesn't split by |
| `Only authors with at least 10 works about kelp since 2020` on a table of kelp works | an `Only` count over other works than the table counts |
| `in [Africa](Q15)` | `in` needs its kind named (the topic, SDG, the collection) |
| `rank ...`, `break down ...`, `workz ...` | unknown entity type: every query starts with `get` and names works, things, or a table's numbers |
| `...; then, group those works by year` after a sentence | OQL has no steps after a sentence: write the table, `get the count of works about kelp by year` |

**Conditions:**

| You wrote | OQL says |
|---|---|
| `institution is [Harvard]` | needs its OpenAlex ID: `[Harvard University](I136199984)` |
| `type is (article review)` | two values with no connective: add `or` (or `and` if you mean both) |
| `type is article review` | more than one value needs parentheses |
| `type is (article, review)` | values in a group are separated by `or`/`and`, not commas |
| `type is article language is en` | two conditions with no AND/OR between them |
| `year >= (2019 or 2020)` | a comparison takes exactly one bound |
| `retracted is (true or false)` | a yes/no field takes exactly one value |
| `work is in collection (col_a or col_b)` | one collection per clause |
| `title-abstract is similar to kelp` | needs one quoted passage |
| `year is 2019-2023` | numeric ranges were removed: `year >= 2019 and year <= 2023` |
| `published after 2021-06-01` | ambiguous for a date: `published since 2021-06-02`, or `since 2021-06-01` to include it |
| `title contains (cancer)` | `contains` was renamed: use `has` |
| `pub_year is 2020` | unknown field |
| `type is`, `type article`, `year is 20x` | a missing value, a missing operator, not a number |
| a missing `)`, `"` or `]` | close it |

**Searches:**

| You wrote | OQL says |
|---|---|
| `title has climate change` | two or more search terms need parentheses or quotes |
| `cancer~1` | `~` is not an OQL operator: for words near each other, `(smart and phone within 3 words of each other)` |
| `dog\|cat` | `\|` is not an OQL operator: `(dog or cat)` |
| `\kelp` | a backslash has no meaning: remove it |
| `*cycle` | a leading wildcard is not supported |
| `ab*` | a wildcard needs at least 3 leading characters |
| `(smart* and phone within 3 words of each other)` | quote the wildcard term |
| `("smart" and phone within 3 words of each other)` | proximity terms are all bare or all quoted |
| `("smart" within 3 words of each other)` | proximity names at least two words and the distance |
| `(stemmed "bar*")` | drop `stemmed` so the wildcard runs on exact text |

**The general form:**

| You wrote | OQL says |
|---|---|
| `then calculate count` | "calculate" doesn't start a step; lists the steps |
| `then, keep groups where ...` | `keep` isn't a step: filter on a count in the start, or download the table |
| a step after `summarize` | the summary must be the last step |
| `group those authors by year` on works | this query holds works: write `those works` |
| `group those works by FWCI` | a decimal can't split by value: use bins |
| `summarize using authors count` | a field, not a calculation: `mean authors count` |
| `compare ...` after a split | a comparison comes before any other split |
| `h-index` with no split by author | `h-index` belongs to each author: split by author |
| a walk from authors to institutions | a walk out starts from works: walk back to their works first |
| a set of the wrong kind | the field takes one kind; the set returns another |
| a set of over 450,000 IDs | narrow the set, or save it as a collection |

**Values** (`invalid_value`): a value from a closed vocabulary must be a member of it, and an ID must have the right shape ([below](#value-domain-validation)).

## Canonical formatting

**A sentence is always one line**, however long. The API returns it as both `oql` and `oql_oneline`.

**The general form fits 80 columns on one line when it can.** A longer one is laid out over several lines in `oql`, and `oql_oneline` keeps it on one line. The parser ignores whitespace, so both are the same query. The rules:

- The start and each step go on their own lines, every line but the last ending in `;`.
- A long `where` breaks at its top-level `and` and `or`, which lead each continuation line, indented 2 spaces.
- A parenthesized group of conditions that doesn't fit opens with `(` at the end of its line, puts its members one level deeper (2 more spaces), each continuation led by its `and` or `or`, and closes with `)` on its own line at the group's indent.
- A long thing-first start breaks before its verb (`who published`), indented 2 spaces.
- A long `compare` puts `using ...` and `by ...` on their own lines, indented 2 spaces, and the compared items one per line (`versus ...`) if they still don't fit.
- A long `summarize` step puts `using ...` on its own line, and a long group filter puts one condition per line (`  where ...`, `  and ...`).
- A single clause never breaks, however long: a value group or a search string stays on its line.

This is the `oql` field for a query one line can't hold:

```
get works where institution is [Harvard University](I136199984)
  or funder is [National Institutes of Health](F4320332161);
then, group those works by continent;
finally, summarize using count
```

**Canonical spelling:**

- Keywords are lowercase; search operators are capitals (`AND`, `OR`, `NOT`).
- Entities and vocabulary values are links with names (`[English](en)`).
- One value or one search word has no parentheses; several share one pair.
- Numbers and years read in words (`is at least 100`, `since 2020`, `from 2018–2025` with an en dash).
- Lists of three or more take an Oxford comma.
- A default order is never written.

## Attributes and values

OQL field names, the columns they map to, value types and valid verbs are owned by the **properties registry** ([`/properties`](https://api.openalex.org/properties)), not by this spec. OQL's grammar is column-agnostic, as the OQO is. API column names work as fields too (`publication_year`, `primary_topic.id`); the echo uses the OQL names.

### Value-domain validation

OQL is **readable in form but strict in values**: a column whose values come from a *closed* vocabulary must carry a member of it. Name matching is a natural-language layer's job, never raw OQL's. So `country is Canada` (a name, not the code) and `country is 42` are errors (`invalid_value`), not queries that silently match nothing. They are not resolved to `CA`: the message offers "did you mean 'ca'?" and the query is still refused.

The closed vocabularies (keyed by the property's `entity_type`; a value validates if and only if it can be rendered with a name):

| `entity_type` | canonical value | valid / invalid |
|---|---|---|
| `countries` | ISO 2-letter code | `US`, `GB` / `UK`, `Canada`, `42` |
| `languages` | ISO 2-letter code | `en` / `english` |
| `sdgs` | number `1`–`17` | `13` / `99` |
| `work-types` | type code | `article`, `review` / `boguskind` |
| `oa-statuses` | status code | `gold`, `green` / `sparkly` |
| `continents` | Wikidata ID | `Q15` |
| `domains` | number (4 in all) | `2` / `99999`, `social sciences` |
| `fields` | number (26 in all) | `27` / `99999`, `medicine` |
| `subfields` | number (252 in all) | `2712` / `99999` |

`GB` is the code for the United Kingdom; `UK` is not a valid code. Every value in a group is checked on its own. Search text is never checked against a vocabulary.

### ID-shape validation

The open ID entities (authors, works, institutions, sources, publishers, funders, topics, concepts, awards) have millions of members, so a value is checked for the right **ID shape** instead. `institution is W5` is an `invalid_value` error: `W5` is a works ID, and institutions IDs start with `I`. A value that isn't an ID at all (`institution is Canada`) is refused the same way. The URL forms of an ID (`I5`, `institutions/I5`, `https://openalex.org/I5`) all validate; only the entity letter is enforced.

| `entity_type` | prefix | `entity_type` | prefix |
|---|---|---|---|
| `works` | `W` | `funders` | `F` |
| `authors` | `A` | `topics` | `T` |
| `institutions` | `I` | `concepts` | `C` |
| `sources` | `S` | `awards` | `G` |
| `publishers` | `P` | | |

Collections use their own verb (`is in the collection`), so a `col_...` value is not shape-checked. Keywords and the numeric classifications have no letter prefix and are not shape-checked.

## The case corpus

This is a **cases-first** specification: the normative truth is a corpus of worked `(OQL, OQO)` pairs, machine-checked against the implementation. The rules in this prose generalize the cases; when the prose and a case disagree, the case wins. Each case either round-trips cleanly, raises a named [error](#diagnostics) with a fix, or documents a known boundary. Browse worked examples in the [cases browser](https://openalex.org/query/oql/cases).

## Not in the language yet

- `Only` and `Show` take counts and the groups' own fields, not other numbers (download the table to filter a mean).
- A second walk out in one query, and splitting each walked thing's works further.
- Three splits in a sentence, and an order in the general form.
- Fuzzy matching.
- Name lookup inside the parser: names in links are decoration, and IDs count.

## Conformance

The [round-trip invariant](#the-canonical-triple) is the spec's runnable contract. A reference implementation is machine-checked over the [case corpus](#the-case-corpus): every round-trip case must go `OQO → OQL → OQO` to the identity, and every error case must raise its named error. An implementation conforms if it passes the corpus.

## Related documentation

- **[OQL overview](https://help.openalex.org/access/oql/)**: the readable tour, every construct with a copyable example.
- **[OQO](https://help.openalex.org/access/oqo-schema/)**: the canonical query object OQL is written over, with its JSON Schema.
- **[OQL API](https://help.openalex.org/api/oql/)**: running and translating OQL over HTTP.
- **[Cases browser](https://openalex.org/query/oql/cases)**: worked examples, browsable.

## Formal grammar

The grammar below is in W3C-EBNF. It describes the **canonical form**, the text the echo writes, read from the parser and renderer. The parser reads more spellings than this (operators like `>=`, bare IDs, names left out of links, phrase parts in any order, any letter case of keywords), and every one comes back in this form. A quoted string of several words is that sequence of words.

```ebnf
/* OQL (OpenAlex Query Language): reference grammar, canonical form, 2026-10-23. */

statement     ::= sentence | general

/* ===================== Sentences ===================== */

sentence      ::= list | table

list          ::= 'get' works ( ',' worksOrder )?
                | 'get' things ( ',' thingsOrder )?

/* A table; with no `by`, one row (no order, no Show, no Only). The word before
   the works phrase follows the last number: `to` after `sum of citations`,
   `for` after `sum of APCs paid`, else `of`. */
table         ::= 'get' 'the' numbers ( 'of' | 'to' | 'for' ) works
                  ( 'by' splits ( ',' tableOrder )? ( '.' ( show only* | only+ ) )? )?

show          ::= 'Show' ownField ( 'and' ownField )? '.'
only          ::= 'Only' thingNoun 'with' countWords NUMBER works '.'
countWords    ::= 'more than' | 'at least' | 'fewer than' | 'at most'

/* ---------- The works phrase, in canonical order ---------- */
works         ::= possessive? adjective* typeNoun time? search* citing* place*
                  people? role? sits* published? funded? license?
                  ( 'where' conditions )?

possessive    ::= link "'s"                 /* one institution, country or author */
adjective     ::= 'open access' | 'closed access' | 'retracted' | 'non-retracted'
                | 'top 1% cited' | 'top 10% cited'
typeNoun      ::= 'works' | 'all works' | 'articles' | 'reviews' | 'preprints' | 'books'
                | 'book chapters' | 'datasets' | 'conference papers' | 'dissertations'
                | 'editorials' | 'letters' | 'reports'
time          ::= ( 'since' | 'from' | 'before' | 'through' ) YEAR
                | 'from' YEAR '–' YEAR
                | ( 'since' | 'through' ) DATE
                | 'from' DATE 'through' DATE
search        ::= 'about' searchString
                | 'with' searchString 'in' searchPlace
searchPlace   ::= 'the title' | 'the abstract' | 'the full text' | 'the title or abstract'
citing        ::= 'citing' link | 'cited by' link | 'citing works in the collection' link
place         ::= 'from' link ( 'or' link )*
                | 'from both' link 'and' link
                | 'from all of' linkList3
                | 'co-authored with' link
people        ::= 'by' link | 'co-authored by' ( link 'and' link | linkList3 )
role          ::= 'with' link 'as corresponding author'
sits          ::= 'in' link ( 'or' link )*              /* a source */
                | 'in' kindKey link ( 'or' link )*
                | 'in the collection' link
kindKey       ::= 'SDG' | 'the topic' | 'the subfield' | 'the field' | 'the domain'
published     ::= 'published by' link ( 'or' link )*
funded        ::= 'funded by' link ( 'or' link )*
license       ::= 'under the' link 'license'
linkList3     ::= link ( ',' link )+ ',' 'and' link

/* ---------- The things phrase ---------- */
things        ::= thingNoun thingPart* threshold* ( 'where' conditions )?
thingNoun     ::= 'authors' | 'institutions' | 'companies' | 'countries' | 'sources'
                | 'journals' | 'repositories' | 'publishers' | 'funders' | 'topics'
                | 'fields' | 'subfields'
thingPart     ::= record | except
                | 'in' link                              /* own country or continent */
                | 'in' ( 'the subfield' | 'the field' | 'the domain' ) link
record        ::= ( 'at' | 'in' ) link ( 'in' DIGIT '+' 'years' )? time?
                | ( 'never at' | 'never in' ) link
                /* an author's own record: `at` an institution, `in` a country */
except        ::= 'except' ( link | '(' link ( ',' link )* ')' )
threshold     ::= 'with' ownNumber numberWords NUMBER
ownNumber     ::= 'an h-index' | 'an i10-index' | 'a works count' | 'a citation count'
numberWords   ::= 'above' | 'at least' | 'below' | 'at most'
ownField      ::= 'h-index' | 'works count'

/* ---------- Numbers ---------- */
numbers       ::= number | number 'and' number | number ( ',' number )+ ',' 'and' number
number        ::= 'count' | 'share' | 'sum of citations' | 'sum of APCs paid'
                | ( 'mean' | 'median' ) ( 'FWCI' | 'citations' )
                | 'percent' yesNoNumber
yesNoNumber   ::= 'open access' | 'retracted' | 'top 1% cited' | 'top 10% cited'
                | 'with an abstract' | 'with full text' | 'with a DOI'

/* ---------- Splits and which groups ---------- */
splits        ::= split ( 'and' split )?            /* two different splits at most */
split         ::= 'year' time?
                | fieldSplit valueSet?
                | thingSplit ( valueSet | groupPart* )
fieldSplit    ::= 'type' | 'language' | 'open access' | 'open access status' | 'retracted'
                | 'topic' | 'subfield' | 'field' | 'domain' | 'SDG' | 'corresponding author'
thingSplit    ::= 'author' | 'institution' | 'company' | 'country' | 'journal' | 'source'
                | 'repository' | 'publisher' | 'funder'
valueSet      ::= 'in' '(' value ( ',' value )* ')'    /* up to 100 */
                | 'in the collection' link
groupPart     ::= record | except | 'in' link | threshold

/* ---------- Orders ---------- */
worksOrder    ::= 'most cited first' | 'least cited first' | 'most cited (age-adjusted) first'
                | 'newest first' | 'oldest first' | 'best matches first'
                | 'highest FWCI first' | 'lowest FWCI first'
                | 'alphabetical by title' | 'reverse alphabetical by title'
                | fieldOrder
thingsOrder   ::= ( 'highest' | 'lowest' ) ( 'h-index' | 'i10-index' ) 'first'
                | 'lowest works count first' | 'most cited first' | 'least cited first'
                | fieldOrder
fieldOrder    ::= ( 'highest' | 'lowest' ) field 'first'          /* a number field */
                | ( 'latest' | 'earliest' ) field 'first'         /* a date field */
                | field ( 'first' | 'last' )                      /* a yes/no field */
                | 'reverse'? 'alphabetical by' field              /* text or a code */
                | 'in' 'reverse'? field 'ID order'                /* an ID field */
tableOrder    ::= ( 'highest' | 'lowest' ) tableColumn? 'first'   /* no name: one number */
                | ( 'most' | 'fewest' ) 'works first'
                | ( 'newest' | 'oldest' ) 'first'                 /* first split is year */
                | 'reverse'? 'alphabetical by' splitWord
                | 'in' 'reverse'? splitWord 'ID order'
tableColumn   ::= number | 'h-index' | 'i10-index' | 'works count' | 'citation count'
splitWord     ::= fieldSplit | thingSplit

/* ===================== Conditions ===================== */

conditions    ::= operand ( ( 'and' | 'or' ) operand )*
                /* and binds tighter than or; the echo writes every grouping */
operand       ::= '(' conditions ')' | clause

clause        ::= field ( 'is' | 'is not' ) valueOrGroup
                | field 'is' numberWords NUMBER
                | searchField 'has' searchString
                | searchField 'is similar to' '(' STRING ')'
                | 'published' ( 'since' | 'before' | 'after' | 'in' | 'through' ) ( YEAR | DATE )
                | dateField 'since' DATE                          /* `added since`, `updated since` */
                | yesNoClause
                | field ( 'is' | 'is not' ) 'in the collection' link
                | field ( 'is' | 'is not' ) 'in the set' '(' setPhrase ')'
                | relationClause

valueOrGroup  ::= value | valueGroup
valueGroup    ::= '(' valueItem ( ( 'and' | 'or' ) valueItem )+ ')'
valueItem     ::= 'not'? ( value | valueGroup )
value         ::= link | NUMBER | WORD | 'unknown'

yesNoClause   ::= "it's" 'not'? yesNoWord
                | 'it' ( 'has' | "doesn't have" ) flagNoun
yesNoWord     ::= 'open access' | 'retracted' | 'top 1% cited' | 'top 10% cited'
                | 'from the global south'
flagNoun      ::= 'a DOI' | 'an ORCID' | 'an abstract' | 'full text'

relationClause ::= 'it cites a work in the set' '(' setPhrase ')'
                | "it doesn't cite any work in the set" '(' setPhrase ')'
                | "it's cited by a work in the set" '(' setPhrase ')'
                | "it isn't cited by any work in the set" '(' setPhrase ')'
                | "it's related to a work in the set" '(' setPhrase ')'
                | "it isn't related to any work in the set" '(' setPhrase ')'
                | "it's related to" '(' link ')'
                | 'it cites' '(' valueItem ( ( 'and' | 'or' ) valueItem )* ')'

/* A set: a query with no `get`, named by what it holds. */
setPhrase     ::= ( 'works' | 'authors of works' | thingNoun ) 'where' conditions

/* ---------- Search strings ---------- */
searchField   ::= 'title' | 'abstract' | 'title-abstract' | 'title-abstract-keywords'
                | 'full text' | 'raw affiliation' | 'byline'
searchString  ::= term | proximity | '(' searchExpr ')'
searchExpr    ::= 'NOT'? searchOperand ( ( 'AND' | 'OR' | 'NOT' ) searchOperand )*
searchOperand ::= term | '(' searchExpr ')' | proximity
term          ::= WORD+                  /* a run of bare words: one stemmed node */
                | STRING                 /* exact */
                | 'stemmed' STRING       /* an adjacent phrase, stemmed */
proximity     ::= '(' proxTerms 'within' NUMBER 'words of each other' ')'
proxTerms     ::= proxTerm 'and' proxTerm | proxTerm ( ',' proxTerm )+ ',' 'and' proxTerm
proxTerm      ::= WORD+ | STRING         /* all bare or all quoted */

/* ===================== The general form ===================== */

general       ::= start ( ';' ( 'then,' | 'finally,' ) step )*
                /* `then,` before each step, `finally,` before the last of two or more */

start         ::= 'get' 'works' corpus? ( 'where' conditions )?
                | 'get' thingNoun ( 'where' conditions )? thingVerb
                  ( countWords NUMBER )? 'works' 'where' conditions
corpus        ::= '(' ( 'all corpora' | 'expansion corpus' ) ')'
thingVerb     ::= 'who published' | 'that published' | 'that funded' | 'of'
                | 'who were corresponding authors of' | 'that were corresponding institutions of'

step          ::= splitStep | compareStep | summaryStep | sampleStep | walkStep

splitStep     ::= 'group those works' firstSplit ( ( ',' | ','? 'and' ) laterSplit )*
firstSplit    ::= ( 'by' field | 'into' field bins ) groupFilter?
laterSplit    ::= ( 'by'? field | 'by' field bins ) groupFilter?   /* up to three splits */
bins          ::= 'bins at' '(' NUMBER ( ',' NUMBER )* ')' | 'bins of' NUMBER
groupFilter   ::= 'where' groupCondition ( ( 'and' | 'or' ) groupCondition )*
groupCondition ::= measure 'of those works' 'is' numberWords NUMBER
                | clause                                   /* the groups' own fields */

compareStep   ::= 'compare' compared ( 'versus' compared )+
                  ( 'using' measures )? ( 'by' laterSplit ( 'and' laterSplit )* )?
                | 'compare each' field 'in the collection' link ( 'using' measures )?
compared      ::= conditions
                /* a yes/no field alone is true; `is` may go unsaid before a value;
                   a later item may drop the field it shares with the one before */

summaryStep   ::= 'summarize' scope? 'using' measures         /* always the last step */
scope         ::= 'each' WORD | 'all those' WORD               /* `each author`, `all those works` */
measures      ::= measure | measure 'and' measure | measure ( ',' measure )+ ',' 'and' measure
measure       ::= 'count'
                | ( 'mean' | 'median' | 'sum' | 'min' | 'max' ) field
                | 'percent' field
                | 'percent of those works'
                | ownField

sampleStep    ::= 'sample' NUMBER 'of those works' ( 'with seed' ( NUMBER | WORD ) )?

walkStep      ::= 'get each' WORD 'of those works' ( 'where' conditions )?
                | 'get' WORD 'of those works'
                | 'get all that' WORD "'s works" ( 'where' conditions )?
                | 'get all those' WORD "' works"

/* ===================== Tokens ===================== */

link          ::= '[' NAME ']' '(' ID ')'
field         ::= WORD+                  /* an OQL field name from the properties registry */
dateField     ::= WORD
YEAR          ::= DIGIT DIGIT DIGIT DIGIT
DATE          ::= YEAR '-' DIGIT DIGIT '-' DIGIT DIGIT
NUMBER        ::= DIGIT+ ( ',' DIGIT DIGIT DIGIT )* ( '.' DIGIT+ )?
DIGIT         ::= [0-9]
ID            ::= [A-Za-z0-9_.-]+
NAME          ::= [^#x5D]*               /* runs to the first `]`; ignored on input */
STRING        ::= '"' [^"]* '"'
WORD          ::= [^#x20#x22#x28#x29#x5B#x5D#x2C]+
```
