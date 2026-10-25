# The OQL guide

> Generated from help.openalex.org/access/oql/ (openalex-help `content/access/oql.md`) by
> oxjobs #1589 `work/make_upstream_guide.py`. Edit the help page, then regenerate.

**OQL, the OpenAlex Query Language, lets you ask OpenAlex for works, people, institutions and journals, and for numbers about them, in plain English.** A query is one sentence:

```
get the count of works about kelp by year since 2000
```

You can read that aloud and know what it returns: how many works about kelp came out each year since 2000. That's the point: a query you can paste into a paper's methods section, that a reader understands, and that anyone can run again for the same answer.

**Where to run it:**

- **On the website:** switch to the **OQL tab** at the top of the [search page](https://openalex.org). Valid queries run as you type. The easiest way to experiment.
- **On the API:** `https://api.openalex.org/?oql=<your query>`. The query names what it gets (`get works ...`, `get authors ...`), so it goes to the API **root**, not `/works`. See the [OQL API](https://help.openalex.org/api/oql/).
- **Check before you run:** `https://api.openalex.org/query/oql/<your query>` is free. It says whether the query is valid (and if not, how to fix it), how long it should take and what it will cost, and it gives the query back in the form shown on this page.

**OQL shows every query back in one form**, the form on this page, whatever you typed. Type `year >= 2020` and the echo says `since 2020`; type a bare ID like `I63966007` and it says `[Massachusetts Institute of Technology](I63966007)`. So you never have to remember the exact wording: write it close enough, and read the echo.

## Two shapes

Every query starts with `get`, and every query returns one of two shapes:

| Shape | The sentence | Example |
|---|---|---|
| **A list of records**: one row per work, or per thing chosen by its own fields | `get <works>[, <order>]` or `get <things>[, <order>]` | `get works about kelp, most cited first` |
| **A table of groups**: numbers about a set of works, one row per group | `get the <numbers> of <works> by <splits>[, <order>]` | `get the count of works about kelp by country` |

A table with no split is one row, the smallest table: `get the count of [University of Kansas](I146416000)'s works`. Two short sentences can follow a table: `Only ...` keeps the groups above a count, and `Show ...` adds the groups' own fields:

```
get the count and mean FWCI of works about kelp by institution in [Sweden](SE), highest mean FWCI first. Only institutions with at least 10 works about kelp.
get the count of works about "latent dirichlet allocation" by author. Show h-index.
```

The order is only ever the words after the last comma, so changing the order never changes the rest of the sentence.

## Describing works

Lists and tables describe their works with the same words: `get works since 2020 about kelp` and `get the count of works since 2020 about kelp by country` are about the same works. The parts go in this order, and the echo puts them back in it:

| # | Part | Examples |
|---|---|---|
| 1 | Whose works, when one institution, country or person defines the set | `[University of Kansas](I146416000)'s works`, `[Kenya](KE)'s works`, `[Jason R Priem](A5023888391)'s works` |
| 2 | Yes/no words | `open access`, `closed access`, `retracted`, `non-retracted`, `top 1% cited`, `top 10% cited` |
| 3 | The type | `works` (every type), `articles`, `reviews`, `preprints`, `datasets`, `books`, `book chapters`, `conference papers`, `dissertations`, `editorials`, `letters` |
| 4 | Time | `since 2020`, `from 2022`, `before 2010`, `from 2018–2025`, `from 2020-10-01 through 2021-09-30` |
| 5 | What it's about | `about kelp`, `with conjugal in the title` |
| 6 | Citations | `citing [The state of OA: a large-scale analysis of the…](W2741809807)`, `cited by [...](W2741809807)` |
| 7 | Where the authors are | `from [Africa](Q15)`, `co-authored with [Massachusetts Institute of Technology](I63966007)`, `with [Jason R Priem](A5023888391) as corresponding author` |
| 8 | Where the work sits | `in [Nature](S137773608)`, `in SDG [Climate action](13)`, `in the topic [CRISPR and Genetic Engineering](T10878)` |
| 9 | Publisher, funder, license | `published by [Elsevier BV](P4310320990)`, `funded by [National Institutes of Health](F4320332161)`, `under the [CC-BY](cc-by) license` |
| 10 | Anything else, after `where` | `where language is [English](en) and citation count is at least 100` |

All together:

```
get [University of British Columbia](I141945490)'s open access articles since 2020 about kelp, most cited first
```

**Entities are links:** the name in brackets, the OpenAlex ID in parentheses. The ID is what counts; the name is optional when you type, and the echo fills it in. Countries use their two-letter code (`[Kenya](KE)`), continents their ID (`[Africa](Q15)`, `[Europe](Q46)`), and closed vocabularies their code (`[review](review)`, `[English](en)`).

### Who: institutions, countries and people

| Example | Meaning |
|---|---|
| `get [Massachusetts Institute of Technology](I63966007)'s works since 2020` | works with an author at MIT (or one of its sub-units) |
| `get works from [Massachusetts Institute of Technology](I63966007) or [Stanford University](I97018004)` | either one |
| `get works from both [University of Oxford](I40120149) and [University of Cambridge](I241749)` | both on the same work |
| `get works from all of [University of Oxford](I40120149), [University of Cambridge](I241749), and [Imperial College London](I47508984)` | all three on the same work |
| `get works about malaria from [Africa](Q15)` | any author in an African country |
| `get works co-authored by [Jason R Priem](A5023888391) and [Heather Piwowar](A5048491430)` | both people are authors |
| `get works with [Jason R Priem](A5023888391) as corresponding author` | the corresponding author |

`co-authored with [X]` says the same as `from [X]`, and reads better beside a split by institution: `get the count of works since 2015 co-authored with [Christian-Albrechts-Universität zu Kiel](I32021983) by company` lists the companies Kiel writes with.

### Time

Years read in words, right after the type: `since 2020` (2020 or later), `from 2022` (that year), `before 2010` (2009 or earlier), `from 2018–2025` (both included). Full dates work the same way when you need them: `get works from 2020-10-01 through 2021-09-30 about kelp`. In a table split by year, the years go after `by year` instead: `get the count of [University of Florida](I33213144)'s works by year since 2004`.

`added since` (when OpenAlex added the work; needs a paid plan) goes after `where`: `get [Massachusetts Institute of Technology](I63966007)'s works where added since 2026-10-01`.

### What it's about: searching

`about` searches titles, abstracts and keywords, which is also openalex.org's default. To search one place, name it:

| Example | Searches |
|---|---|
| `get works about kelp` | title, abstract, and works tagged with a [keyword](https://help.openalex.org/api/searching/#keywords-in-search) the search names |
| `get works with conjugal in the title` | the title |
| `get works with conjugal in the abstract` | the abstract |
| `get works with conjugal in the title or abstract` | both, no keywords |
| `get works with "OpenAlex" in the full text` | title, abstract and full text |
| `get works where raw affiliation has ("Max Planck" AND Leipzig)` | the affiliation strings as printed |
| `get works where byline has Priem` | the author names as printed |

The search string is portable, exactly as a systematic review would report it: capital `AND`, `OR` and `NOT`, parentheses for grouping. One word or one phrase needs no parentheses. The one rule to internalize: **bare words are stemmed, quotes mean exact.** `about kelp` also matches *kelps*; `"climate change"` matches only that exact phrase.

| Example | Meaning |
|---|---|
| `get works about ((asthma OR wheeze) AND child*)` | Boolean, with a wildcard |
| `get works with ((asthma OR wheeze) NOT (child OR pediatric)) in the title or abstract` | `NOT` leaves works out |
| `get works about "climate change"` | **exact** phrase (stemming off) |
| `get works with (stemmed "genome editing") in the title` | a phrase kept together that *keeps* stemming |
| `get works with psoriat* in the title` | `*` is any characters; `?` is exactly one (`wom?n`); neither may start a word, and `*` needs at least 3 characters before it |
| `get works about ("smart" and "phone" within 3 words of each other)` | proximity: both terms within N words, any order |
| `get works where title-abstract is similar to ("ocean acidification effects on coral reefs")` | semantic search: by meaning, not keywords (returns the 50 closest) |

**OQL never adds words you didn't write.** No synonyms, no expansions: the search is exactly your string.

### Citations

| Example | Meaning |
|---|---|
| `get works citing [The state of OA: a large-scale analysis of the…](W2741809807)` | works whose reference list includes that paper |
| `get works cited by [The state of OA: a large-scale analysis of the…](W2741809807)` | the works in its reference list |
| `get works where it's related to ([The state of OA: a large-scale analysis of the prevalence and impact of Open Access articles](W2741809807))` | OpenAlex's "related works" for it |
| `get works citing works in the collection [Example: altmetrics papers](col_8yWKmRNyEr)` | works citing any work in a [collection](#collections) |

A long work title is cut short in the echo (at 48 characters); the ID is what counts. To cite (or not cite) a whole set of works, see [the general form](#when-a-sentence-cant-say-it-the-general-form).

### Where the work sits: journals, topics, funders, licenses

| Example | Meaning |
|---|---|
| `get works since 2024 in [Nature](S137773608)` | published in that journal (its primary location) |
| `get works since 2024 in SDG [Climate action](13)` | tagged with that Sustainable Development Goal |
| `get works since 2024 in the topic [CRISPR and Genetic Engineering](T10878)` | primary topic (also `in the subfield`, `in the field`, `in the domain`) |
| `get works from 2022 in the field [Computer Science](17)` | primary topic's field |
| `get works from 2024 published by [Elsevier BV](P4310320990)` | the publisher |
| `get works since 2020 funded by [Wellcome Trust](F4320311904) or [National Institutes of Health](F4320332161)` | either funder |
| `get works from 2024 under the [CC-BY](cc-by) license` | the license |

A value whose kind isn't obvious names its kind: `SDG`, `the topic`, `the subfield`, `the field`, `the domain`, `the collection`, `the ... license`.

### Anything else: `where`

Anything the phrases above don't say goes last, after `where`, as conditions joined with `and` and `or`:

| Example | Meaning |
|---|---|
| `get works about kelp where source type is [journal](journal) and language is [English](en)` | a field is a value |
| `get [Massachusetts Institute of Technology](I63966007)'s works where type is not ([review](review) or [editorial](editorial))` | anything but: negate on the verb; several values share one pair of parentheses |
| `get works about kelp where institution type is ([company](company) or [government](government))` | one of several values |
| `get [Massachusetts Institute of Technology](I63966007)'s works where citation count is at least 1000` | numbers in words: `is above`, `is at least`, `is below`, `is at most` |
| `get [Kenya](KE)'s works from 2023 where FWCI is above 10` | decimals work too |
| `get [Ghana](GH)'s works where it has a DOI and it doesn't have an abstract` | yes/no fields read as sentences about the work |
| `get works from 2024 about kelp where institution is unknown` | the field is empty |
| `get works where ORCID is 0000-0001-6187-6610` | other schemes' IDs: `DOI is 10.1038/nature12373`, `ROR ID is 00ghzk478`, `PMID is 29456894`, `ISSN is 0028-0836` |
| `get works where institution is [Massachusetts Institute of Technology](I63966007) or funder is [National Institutes of Health](F4320332161)` | OR across different fields |

Group conditions with parentheses. `and` binds tighter than `or`, and the echo always writes the parentheses, so nothing is left to guess:

```
get works where (published before 2000 and title-abstract has "global warming") or (title-abstract has "climate change" and published after 2020)
```

Nesting and OR across *different* fields are what the classic URL syntax can't express. Inside a `where`, searches use `has` with the field name (`title has`, `abstract has`, `title-abstract has`, `title-abstract-keywords has`, `full text has`, `raw affiliation has`, `byline has`) and years read `published since 2020`, `published before 2000`, `published after 2020`, `published in 2023`, `published from 2015 through 2024`.

**Fields for `where`, on works:** type, language, open access, open access status, license, retracted, has DOI, has abstract, has full text, has ORCID, global south, top 1% cited, top 10% cited; institution, institution type, institution country, country, continent, author, corresponding author, corresponding institution, source, source type, publisher, funder, awards, topic (primary), topics (any), subfield, field, domain, keyword, SDG; citation count, FWCI, citation percentile by subfield, reference count, authors count, institutions count, countries count, APC paid; DOI, PMID, ISSN, ORCID, ROR ID; added, updated. API column names (`publication_year`, `primary_topic.id`) work too; the echo uses the OQL names.

## Lists

### Lists of works

End a list with an order after a comma:

| Order | |
|---|---|
| `, most cited first` / `, least cited first` | by citation count |
| `, newest first` / `, oldest first` | by publication date |
| `, highest FWCI first` / `, lowest FWCI first` | by field-weighted citation impact |
| `, alphabetical by title` / `, reverse alphabetical by title` | by title |
| `, best matches first` | by relevance to the search (the default when there's a search, so the echo leaves it out) |

```
get works since 2023 about "large language models", most cited first
get [University of Oxford](I40120149)'s works about (malaria AND vaccine), newest first
get articles about CRISPR where source type is [journal](journal), highest FWCI first
```

With no order, a list with a search comes back best matches first; a list with no search comes back most cited first, adjusted for age.

### Lists of things

Authors, institutions, journals and other things can be listed by their own fields: what's on their own record, not counts of some works. `get authors`, `get institutions`, `get companies`, `get journals`, `get repositories`, `get sources`, `get publishers`, `get funders`, `get topics`:

| Example | Meaning |
|---|---|
| `get authors at [University of British Columbia](I141945490) since 2022 with an h-index above 50` | UBC is on their record in 2022 or later |
| `get authors at [University of British Columbia](I141945490) with an h-index above 50` | UBC is on their record in **any** year |
| `get authors never at [University of British Columbia](I141945490) where last known institution is [University of Washington](I201448701)` | never on their record |
| `get authors with an h-index above 50 where last known institution is [Massachusetts Institute of Technology](I63966007)` | OpenAlex's best guess at where they are now |
| `get authors at [University of Kansas](I146416000) since 2022 where it has an ORCID` | yes/no fields as sentences |
| `get authors where co-author is [Jason R Priem](A5023888391)` | everyone who has written with him |
| `get institutions in [Austria](AT), most cited first` | institutions in a country, with an order |
| `get companies in [Sweden](SE), most cited first` | one type of institution |
| `get institutions in [Germany](DE) where collaborator is not [Massachusetts Institute of Technology](I63966007)` | never co-authored with MIT |
| `get institutions where city is Vienna` | by city |
| `get journals where publisher is [Elsevier BV](P4310320990)` | a publisher's journals |
| `get journals in [Kenya](KE)` | journals by country |
| `get funders in [Kenya](KE)` | funders by country |
| `get topics in the field [Computer Science](17)` | topics in a field |

`at [X]` reads each author's own record (the institutions on their profile, with years), not the papers' affiliations. Bare `at [X]` means any year, so it also finds people whose record lists X once, long ago or by mistake; for the people there now, write a window (`at [X] since 2022`) or `where last known institution is [X]`.

**Orders for things:** `, highest h-index first`, `, lowest h-index first`, `, highest i10-index first`, `, lowest i10-index first`, `, most cited first`, `, least cited first`, `, lowest works count first`. With no order, things come back most works first.

**Things' own fields:** authors: h-index, i10-index, works count, citation count, last known institution, has ORCID, co-author; institutions: country, continent, type, region, city, global south, works count, h-index, collaborator; sources: type, publisher, ISSN, works count, h-index, 2-year mean citedness.

To rank things by a number about *some* works (who publishes most on kelp), use a table: the next section.

## Tables of groups

```
get the <numbers> of <works> by <split>[ and <split>][, <order>]
```

A table takes a set of works, splits it into groups, and gives numbers for each group, one row per group. With two splits, one row per pair (each year-and-country), with a column for each split and each number.

### Numbers

Join numbers with `and` (an Oxford comma for three or more). A number covers the matching works in each group.

| Number | Meaning |
|---|---|
| `count` | how many works |
| `share` | each row's slice of the group one level up: of the whole set with one split; of each year with `by year and country` |
| `mean FWCI`, `median FWCI`, `mean citations`, `median citations` | averages over the works |
| `sum of citations` | total citations to the works (`the sum of citations to works ...`) |
| `sum of APCs paid` | total article processing charges paid (`the sum of APCs paid for works ...`) |
| `percent <yes/no word>` | the rate within each row: `percent open access`, `percent retracted`, `percent with an abstract`, `percent with a DOI`, `percent top 1% cited`, `percent top 10% cited` |

```
get the count of [University of Kansas](I146416000)'s works
get the count and mean citations of works from 2022 in the field [Computer Science](17)
get the sum of APCs paid for [University of Kansas](I146416000)'s works
get the count, mean FWCI, and percent open access of works about kelp by country
get the median FWCI and median citations of works about kelp by year
```

### Splits

One or two, joined with `and`:

- **Fields of the works:** `year`, `type`, `language`, `open access`, `open access status`, `retracted`, `topic`, `subfield`, `field`, `domain`, `SDG`.
- **Things:** `author`, `corresponding author`, `institution`, `company`, `country`, `journal`, `source`, `repository`, `publisher`, `funder`.

```
get the count of works about "quantum computing" by country
get the count and percent retracted of works in [Heliyon](S2898612692) by year and field
get the count and share of [France](FR)'s works by year since 2013 and open access status
get the count of [Kenya](KE)'s works by open access
```

Year is always the x-axis wherever you write it. A yes/no split gives two rows (`open access` and `not open access`). Splits by continent, institution type, source type, license, keyword or global south, number bins, and three splits need [the general form](#when-a-sentence-cant-say-it-the-general-form).

### Which groups

To narrow a split by things, describe the groups right after the split word:

| Example | Groups |
|---|---|
| `get the count of works about kelp by author at [University of British Columbia](I141945490) since 2022` | authors whose own record has UBC since 2022 |
| `get the count of works about kelp by author in [Norway](NO)` | authors whose own record is in Norway |
| `get the count of works about kelp by institution in [Canada](CA)` | Canadian institutions |
| `get the count of works about kelp by author with an h-index above 40` | authors with an h-index above 40 |
| `get the count and share of top 1% cited articles by year and country in ([United States](US), [China](CN))` | just these countries (up to 100 values) |
| `get the count and mean FWCI of works since 2015 by institution in ([Indian Institute of Technology Bombay](I162827531), [Indian Institute of Technology Delhi](I68891433))` | named institutions side by side |
| `get the count of works about kelp by author in ([Jason R Priem](A5023888391), [Heather Piwowar](A5048491430))` | named people |
| `get the count and mean FWCI of works since 2020 by country in the collection [European Union (EU27)](col_LV29j8URoX)` | the members of a [collection](#collections) |
| `get the count of works from [Kenya](KE) by country except [Kenya](KE)` | everyone but Kenya: Kenya's partner countries |

**Which groups is not which works.** `by author at [UBC](I141945490) since 2022` keeps the people whose record has UBC, and counts all their kelp works, wherever they wrote them. `from [UBC](I141945490) by author` keeps the works with a UBC author, and counts everyone on them, UBC or not:

```
get the count of works about kelp by author at [University of British Columbia](I141945490) since 2022
get the count of works about kelp from [University of British Columbia](I141945490) by author
```

A condition about the people or places goes on the groups. A condition on the works drops papers, not people. Groups chosen by other own fields (`last known institution`, `co-author is not`, `institution type`) are said in the general form; the echo writes it for you:

```
get authors where last known institution is [University of Kansas](I146416000) who published works where title-abstract-keywords has (kelp); then, summarize each author using count
```

### Count floors: `Only`

`Only` keeps the groups with enough of the same works, as its own sentence after the table:

```
get the count of works about kelp by author. Only authors with at least 20 works about kelp.
```

Use one whenever you order by a rate or a mean: a percent or mean ordered highest first puts tiny groups on top (5 works, 100% open access).

### The groups' own fields: `Show`

A thing's own fields (h-index, works count) are not numbers about the works. Add them as columns with `Show`:

```
get the count of works about kelp by author at [University of British Columbia](I141945490) since 2022. Show h-index.
get the count of works about kelp by author. Show h-index and works count.
get the count of works about kelp by institution. Show h-index.
```

Ordering by one (`, highest h-index first`) shows it too.

### Order

The order goes last, after a comma. With none, a table comes back most works first, and years oldest first.

| Order | |
|---|---|
| `, highest <number> first` / `, lowest <number> first` | by any number in the table: `, highest mean FWCI first`, `, highest share first` (with one number: `, highest first`) |
| `, most works first` / `, fewest works first` | by count |
| `, newest first` / `, oldest first` | years |
| `, alphabetical by <split>` | `, alphabetical by country` |
| `, highest h-index first` | by a thing's own field |

```
get the count and mean FWCI of works about kelp by country, lowest mean FWCI first. Only countries with at least 50 works about kelp.
get the sum of citations to works since 2018 about oleogel* by author, highest first
get the count of works about kelp by year, newest first
get the count of works about kelp by year and country, most works first
```

An order sorts every group, not just the first page, and orders two splits as one flat table.

### More examples

```
get the count of works since 2020 about (archaeology AND "deep learning") by journal
get the count of works about kelp by author at [University of British Columbia](I141945490), highest h-index first
get the count and share of all works by SDG
get the count of works from both [University of Oxford](I40120149) and [University of Cambridge](I241749) by year since 2015
get the sum of APCs paid for works funded by [Wellcome Trust](F4320311904) by publisher, highest first
get the count and percent open access of works about kelp by country, highest percent open access first. Only countries with at least 50 works about kelp.
```

`all works` stands for every work when nothing else narrows them (`get the count and share of all works by SDG`).

## Collections

A [collection](https://help.openalex.org/how-to/collections/) is a list you saved: works, institutions, countries, people, a ranking OpenAlex doesn't hold. Use it wherever a value goes; what `in the collection` means depends on what the collection holds:

```
get works in the collection [Example: altmetrics papers](col_8yWKmRNyEr)
get works from 2024 in the collection [European Union (EU27)](col_LV29j8URoX)
get works from 2024 about kelp where country is not in the collection [European Union (EU27)](col_LV29j8URoX)
get works citing works in the collection [Example: altmetrics papers](col_8yWKmRNyEr)
get the count and mean FWCI of works since 2020 by country in the collection [European Union (EU27)](col_LV29j8URoX)
```

The first is the works in a works collection; the second, works from the EU's member countries. A collection of your peer institutions works the same way in a table: `by institution in the collection [My peers](<your collection ID>)` gives one row per peer. Write the collection's ID in parentheses or as a link; a bare `col_...` is an error.

## When a sentence can't say it: the general form

A few questions need more than one sentence: comparing one thing against the rest, sets of works inside a condition, walking from works to their authors and on to all those authors' works, number bins, samples, counts of distinct authors. For these, OQL has a general form. It starts `get works where <conditions>` and adds steps after semicolons: `then,` for each step, `finally,` for the last of two or more. It's fully supported; the echo uses a sentence whenever one exists, and the general form only when none does.

**One against the rest:**

```
get works where published since 2015; then, compare country [India](IN) versus country is not [India](IN) using count and mean FWCI
```

**Sets inside conditions.** A set is a query inside a condition; it names what it holds:

```
get works since 2025 where author is in the set (authors of works where title-abstract has kelp and published since 2022)
get the count of works where it cites a work in the set (works where institution is [University of Kansas](I146416000)) by year
get works from 2024 in the topic [CRISPR and Genetic Engineering](T10878) where it doesn't cite any work in the set (works where institution is [University of Kansas](I146416000))
```

The first finds recent work by anyone who wrote about kelp since 2022; the second, every work citing a Kansas paper, by year (a set fits in a sentence's `where`).

**Walks.** A walk goes from the works to the things related to them, then to *everything* those things did:

```
get works where institution is [University of Kansas](I146416000) and published in 2023; then, get each author of those works; then, get all that author's works; finally, summarize each author using mean FWCI
```

That's each Kansas 2023 author and the mean FWCI of **all** their papers, not just the Kansas ones. One walk out per query.

**Counting distinct things, bins, samples, other numbers:**

```
get authors who published works where topic is [CRISPR and Genetic Engineering](T10878); then, summarize all those authors using count
get works where title-abstract-keywords has (kelp); then, group those works into citation count bins at (1, 10, 100); finally, summarize using count
get works where published in 2020; then, sample 500 of those works with seed 42
get works where author is [Jason R Priem](A5023888391); then, summarize all those works using min date and max date
get works where title-abstract-keywords has (kelp); then, group those works by continent; finally, summarize using count
get works where title-abstract-keywords has (kelp); then, group those works by year; finally, summarize using mean reference count and median authors count
```

The first counts distinct CRISPR authors. Bins at `(1, 10, 100)` give `0`, `1-9`, `10-99` and `100+`; `into FWCI bins of 0.5` gives equal widths. A sample with a seed is the same sample every time. The general form splits up to three ways, by any field (continent, institution type, source type, license, keyword, global south), and takes `mean`, `median`, `sum`, `min` and `max` of any number field and `percent` of any yes/no field.

## What OQL assumes

OQL's text never hides a condition the query carries, with these exceptions: sensible defaults it doesn't spell out.

| Default | What it means |
|---|---|
| `about` | searches the title, the abstract and the keywords |
| The core corpus | every query of works runs on OpenAlex's [core corpus](https://help.openalex.org/data/works/corpus/) unless it asks for another, in the general form: `get works (all corpora) where title-abstract-keywords has (kelp)`, or `(expansion corpus)` |
| Authors with works | lists of authors leave out authors with no works |
| Sub-units count | `from [institution]` and `[institution]'s works` include its sub-units (a university's hospitals and institutes) |
| Primary topic | `in the topic / subfield / field / domain` and splits by them use each work's primary topic, not every topic it has |
| Primary location | `in [journal]` and `by journal` / `by source` use each work's primary location |
| Default orders | a list with a search: best matches first; a list without: most cited first, adjusted for age; things: most works first; a table: most works first, years oldest first |

## Downloading results

A table exports every row, however many there are, the same way a list of works exports every work. On the website, use the download button above the results: the Export dialog shows the price before you start, and you can follow the export in **Settings → Exports**. An export costs the query's price for every 100 rows it writes (1 credit per 100 groups for a filtered set, 10 for a search), and stops if your credits run out.

There's nothing to choose. With no split, the export is the one row, as a CSV. With splits, it's one zip of:

- **`groups.csv`**: every group, one row each (with two splits, one row per pair), so every row stands on its own. Columns are named in OQL words: each split (`institution`, plus `institution id` for things with IDs), then each number (`percent open access`).
- **The summary**: `all-works.csv`, the whole set in one row, and with two splits one CSV per split (`by-institution.csv`, `by-year.csv`). Read these rather than adding up the groups: a work can sit in more than one group (or in none, when it has no year), so groups don't always add up, and a mean of group means is not the mean.

On the API, the two are separate calls: `format=csv` for the groups, and `format=csv&table=summary` for the summary. A single split by a field pages: add `cursor=*` and follow the `X-Next-Cursor` response header (10,000 groups a page) until it's gone.

```
https://api.openalex.org/?oql=get the count and percent open access of [Kenya](KE)'s works by year since 2015&format=csv
```

## Limits, time and price

Two splits in a sentence, three in the general form; up to 100 values in a list; with two splits, up to 10,000 groups per split (one split pages through any number); one walk out per query; about ten seconds a query. Anything over a limit is refused before it runs, with the limit and how to fix it. A table split by author over a broad set of works can be refused as too slow (every author of every 2024 work is about 12 million groups); narrow the works with a topic, a search, a place or fewer years.

A list costs what the same query costs as a URL: 1 credit, or 10 with a search. A table costs what its set of works costs as a list, plus 1 for each lookup of the groups' own records (`at`, `Show h-index`); splits, counts, means and percents add nothing. Walks and compared searches add more. The check tells you the exact price for free, and a response shows what it cost in `meta.cost`. See [Example costs](https://help.openalex.org/access/example-costs/#what-an-oql-calculation-costs).

## OQL never guesses

A query that can't do what it appears to do is refused before it runs, never answered wrong, and the error says how to fix it:

| You wrote | OQL says |
|---|---|
| `by FWCI` | `unknown split by FWCI`, and lists the splits a table takes |
| `the authors count of works ...` | `unknown numbers`, and lists the numbers |
| `, most popular first` | `unknown order`, and lists the orders a list takes |
| `where published after 2021-06-01` | ambiguous for a date: write `published since 2021-06-02`, or `since 2021-06-01` to include it |
| `where type is (article review)` | two values need a connective: `or` (or `and` if you mean both) |
| `by year and country and type` | a table splits two ways at most |
| `[Harvard]` with no ID | needs its OpenAlex ID: `[Harvard University](I136199984)` |
| `title contains (cancer)` | `contains` was renamed: use `has` |
| `rank ...` or `break down ...` | every query starts with `get`: `get the count of works about kelp by country` |
| `...; then, group those works by year` after a sentence | a table is one sentence: `get the count of works about kelp by year` |

## Not in the language yet

`Only` and `Show` take counts and the groups' own fields, not other numbers (filter a mean by downloading the table); a second walk out in one query; splitting each walked thing's works further; three splits in a sentence. And nothing OpenAlex doesn't hold.

## Going deeper

- **[Your first OQL queries](https://help.openalex.org/tutorials/oql/)**: a five-step tutorial, from a list of papers to the people behind a topic.
- **How-tos:** [Benchmarking against peers](https://help.openalex.org/how-to/benchmarking/), [Finding experts and partners](https://help.openalex.org/how-to/finding-experts/), [Tracking trends over time](https://help.openalex.org/how-to/trends-over-time/), [Following citations](https://help.openalex.org/how-to/following-citations/), and [Systematic reviews](https://help.openalex.org/tutorials/systematic-reviews/).
- **[Cases](https://openalex.org/query/oql/cases)**: a browsable library of worked examples, each with its OQL and the underlying query object.
- **[Specification](https://help.openalex.org/access/oql-spec/)**: the formal spec: every rule and edge case, plus the formal grammar.
- **[OQO](https://help.openalex.org/access/oqo-schema/)**: the machine-readable JSON twin of OQL, built for agents and tools.
- **[OQL API](https://help.openalex.org/api/oql/)**: executing and translating OQL over HTTP.

Tell us what's confusing, what's missing, and what you wish you could ask.
