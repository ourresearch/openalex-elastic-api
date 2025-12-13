# Author object

When you use the API to get a [single author](get-a-single-author.md) or [lists of authors](get-lists-of-authors.md), this is what's returned.

### `affiliations`

_List:_ List of objects, representing the affiliations this author has claimed in their publications. Each object in the list has two properties:

* `institution`: a [dehydrated `Institution`](../institutions/institution-object.md#the-dehydratedinstitution-object) object
* `years`: a list of the years in which this author claimed an affiliation with this institution

```json
affiliations: [
    {
        institution: {
            id: "https://openalex.org/I201448701",
            ror: "https://ror.org/00cvxb145",
            ...
        },
        years: [2018, 2019, 2020]
    },
    {
        institution: {
            id: "https://openalex.org/I74973139",
            ror: "https://ror.org/05x2bcf33",
            ...
        },
        years: [2011, 2012, 2013, 2014, 2015, 2016, 2017, 2018, 2019]
    }
]
```

### `cited_by_count`

_Integer:_ The total number :page\_facing\_up: [Works](../works/work-object/) that cite a work this author has created.

```json
cited_by_count: 38 
```

### `counts_by_year`

_List:_ [`Author.works_count`](author-object.md#works\_count) and [`Author.cited_by_count`](author-object.md#cited\_by\_count) for each of the last ten years, binned by year. To put it another way: each year, you can see how many works this author published, and how many times they got cited.

Any works or citations older than ten years old aren't included. Years with zero works and zero citations have been removed so you will need to add those in if you need them.

```json
counts_by_year: [
    {
        year: 2022,
        works_count: 0,
        cited_by_count: 8
    },
    {
        year: 2021,
        works_count: 1,
        cited_by_count: 252
    },
    ...
    {
        year: 2012,
        works_count: 7,
        cited_by_count: 79
    }
]
```

### `created_date`

_String:_ The date this `Author` object was created in the OpenAlex dataset, expressed as an [ISO 8601](https://en.wikipedia.org/wiki/ISO\_8601) date string.

```json
created_date: "2017-08-08"
```

### `display_name`

_String:_ The name of the author as a single string.

```json
display_name: "Jason Priem"
```

### `display_name_alternatives`

_List:_ Other ways that we've found this author's name displayed.

```json
display_name_alternatives: [
    "Jason R Priem"
]
```

### `id`

_String:_ The OpenAlex ID for this author.

```json
id: "https://openalex.org/A5023888391"
```

### `ids`

_Object:_ All the external identifiers that we know about for this author. IDs are expressed as URIs whenever possible. Possible ID types:

* `openalex` (_String:_ this author's [OpenAlex ID](../../how-to-use-the-api/get-single-entities/#the-openalex-id). Same as [`Author.id`](author-object.md#id))
* `orcid` (_String:_ this author's [ORCID](https://orcid.org/) [ID](https://en.wikipedia.org/wiki/RAS\_syndrome). Same as [`Author.orcid`](author-object.md#orcid))
* `scopus` (_String_: this author's [Scopus author ID](https://utas.libguides.com/ManageID/Scopus))
* `twitter` (_String:_ this author's Twitter handle)
* `wikipedia` (_String_: this author's Wikipedia page)

{% hint style="info" %}
Most authors are missing one or more ID types (either because we don't know the ID, or because it was never assigned). Keys for null IDs are not displayed.
{% endhint %}

```json
ids: {
    openalex: "https://openalex.org/A5023888391",
    orcid: "https://orcid.org/0000-0001-6187-6610",
    scopus: "http://www.scopus.com/inward/authorDetails.url?authorID=36455008000&partnerID=MN8TOARS",
},
```

### `last_known_institution` (deprecated)

{% hint style="danger" %}
This field has been deprecated. Its replacement is [`last_known_institutions`](author-object.md#last\_known\_institutions).
{% endhint %}


### `last_known_institutions`

_List:_ List of Institution objects. This author's last known institutional affiliations. In this context "last known" means that we took all the author's [Works](../works/work-object/), sorted them by publication date, and selected the most recent one. If there is only one affiliated institution for this author for the work, this will be a list of length 1; if there are multiple affiliations, they will all be included in the list.

Each item in the list is a [dehydrated `Institution`](../institutions/institution-object.md#the-dehydratedinstitution-object) object, and you can find more documentation on the [Institution](../institutions/institution-object.md) page.

```json
last_known_institutions: [{
    id: "https://openalex.org/I4200000001",
    ror: "https://ror.org/02nr0ka47",
    display_name: "OurResearch",
    country_code: "CA",
    type: "nonprofit",
    lineage: ["https://openalex.org/I4200000001"]
}],
```

### `orcid`

_String:_ The [ORCID](https://en.wikipedia.org/wiki/ORCID) [ID](https://en.wikipedia.org/wiki/RAS\_syndrome) for this author. ORCID is a global and unique ID for authors. This is the [Canonical external ID](../../how-to-use-the-api/get-single-entities/#canonical-external-ids) for authors.

{% hint style="warning" %}
Compared to other Canonical IDs, ORCID coverage is relatively low in OpenAlex, because ORCID adoption in the wild has been slow compared with DOI, for example. This is particularly an issue when dealing with older works and authors.
{% endhint %}

```json
orcid: "https://orcid.org/0000-0001-6187-6610"
```

### `summary_stats`

_Object:_ Citation metrics for this author

* `2yr_mean_citedness` _Float_: The 2-year mean citedness for this source. Also known as [impact factor](https://en.wikipedia.org/wiki/Impact\_factor). We use the year prior to the current year for the citations (the numerator) and the two years prior to that for the citation-receiving publications (the denominator).
* `h_index` _Integer_: The [_h_-index](https://en.wikipedia.org/wiki/H-index) for this author.
* `i10_index` _Integer_: The [i-10 index](https://en.wikipedia.org/wiki/Author-level\_metrics#i-10-index) for this author.

While the 2-year mean citedness is normally a journal-level metric, it can be calculated for any set of papers, so we include it for authors.

```json
summary_stats: {
    2yr_mean_citedness: 1.5295340589458237,
    h_index: 45,
    i10_index: 205
}
```

### `updated_date`

_String:_ The last time anything in this author object changed, expressed as an [ISO 8601](https://en.wikipedia.org/wiki/ISO\_8601) date string. This date is updated for _any change at all_, including increases in various counts.

```json
updated_date: "2022-01-02T00:00:00"
```

### `works_api_url`

_String:_ A URL that will get you a list of all this author's works.

We express this as an API URL (instead of just listing the works themselves) because sometimes an author's publication list is too long to reasonably fit into a single author object.

```json
works_api_url: "https://api.openalex.org/works?filter=author.id:A5023888391",
```

### `works_count`

_Integer:_ The number of :page\_facing\_up: [Works](../works/work-object/) this this author has created.

```json
works_count: 38 
```

{% hint style="info" %}
This is updated a couple times per day. So the count may be slightly different than what's in works when viewed [like this](https://api.openalex.org/works?filter=author.id:A5023888391).
{% endhint %}

### `x_concepts`

{% hint style="danger" %}
`x_concepts` will be deprecated and removed soon. We will be replacing this functionality with [`Topics`](../topics/README.md) instead.
{% endhint %}

_List:_ The concepts most frequently applied to works created by this author. Each is represented as a [dehydrated `Concept`](../concepts/concept-object.md#the-dehydratedconcept-object) object, with one additional attribute:

* `score` (_Float_): The strength of association between this author and the listed concept, from 0-100.

```json
x_concepts: [
    {
        id: "https://openalex.org/C41008148",
        wikidata: null,
        display_name: "Computer science",
        level: 0,
        score: 97.4
    },
    {
        id: "https://openalex.org/C17744445",
        wikidata: null,
        display_name: "Political science",
        level: 0,
        score: 78.9
    }
]
```

## The Dehydrated`Author` object

The `DehydratedAuthor` is stripped-down [`Author`](author-object.md#the-author-object) object, with most of its properties removed to save weight. Its only remaining properties are:

* [`id`](author-object.md#id)
* [`display_name`](author-object.md#display\_name)
* [`orcid`](author-object.md#orcid)
