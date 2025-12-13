# Concept object

{% hint style="warning" %}
These are the original OpenAlex Concepts, which are being deprecated in favor of [Topics](../topics/README.md). We will continue to provide these Concepts for Works, but we will not be actively maintaining, updating, or providing support for these concepts. Unless you have a good reason to be relying on them, we encourage you to look into [Topics](../topics/README.md) instead.
{% endhint %}

These are the fields in a concept object. When you use the API to get a [single concept](../concepts/get-a-single-concept.md) or [lists of concepts](../concepts/get-lists-of-concepts.md), this is what's returned.

### `ancestors`

_List:_ List of concepts that this concept descends from, as [dehydrated Concept](concept-object.md#the-dehydratedconcept-object) objects. See the [concept tree section](../concepts/) for more details on how the different layers of concepts work together.

```json
ancestors: [
    {
        id: "https://openalex.org/C2522767166",
        wikidata: "https://www.wikidata.org/wiki/Q2374463",
        display_name: "Data science",
        level: 1
    },
    {
        id: "https://openalex.org/C161191863",
        wikidata: "https://www.wikidata.org/wiki/Q199655",
        display_name: "Library science",
        level: 1
    },
    
    // and so forth
]
```

### `cited_by_count`

_Integer:_ The number citations to works that have been tagged with this concept. Or less formally: the number of citations to this concept.

For example, if there are just two works tagged with this concept and one of them has been cited 10 times, and the other has been cited 1 time, `cited_by_count` for this concept would be `11`.

```json
cited_by_count: 20248 
```

### `counts_by_year`

_List:_ The values of [`works_count`](concept-object.md#works\_count) and [`cited_by_count`](concept-object.md#cited\_by\_count) for _each_ of the last ten years, binned by year. To put it another way: for every listed year, you can see how many new works were tagged with this concept, and how many times _any_ work tagged with this concept got cited.

Years with zero citations and zero works have been removed so you will need to add those back in if you need them.

```json
counts_by_year: [
    {
        year: 2021,
        works_count: 4211,
        cited_by_count: 120939
    },
    {
        year: 2020,
        works_count: 4363,
        cited_by_count: 119531
    },
    
    // and so forth
]
```

### `created_date`

_String:_ The date this `Concept` object was created in the OpenAlex dataset, expressed as an [ISO 8601](https://en.wikipedia.org/wiki/ISO\_8601) date string.

```json
created_date: "2017-08-08"
```

### `description`

_String:_ A brief description of this concept.

```json
description: "study of alternative metrics for analyzing and informing scholarship"
```

### `display_name`

_String:_ The English-language label of the concept.

```json
display_name: "Altmetrics"
```

### `id`

_String:_ The OpenAlex ID for this concept.

```json
id: "https://openalex.org/C2778407487"
```

### `ids`

_Object:_ All the external identifiers that we know about for this concept. IDs are expressed as URIs whenever possible. Possible ID types:

* `mag` (_Integer:_ this concept's [Microsoft Academic Graph](https://www.microsoft.com/en-us/research/project/microsoft-academic-graph/) ID)
* `openalex` (_String:_ this concept's [OpenAlex ID](../../how-to-use-the-api/get-single-entities/#the-openalex-id). Same as [`Concept.id`](concept-object.md#id))
* `umls_cui` (_List:_ this concept's [Unified Medical Language System](https://www.nlm.nih.gov/research/umls/index.html) [Concept Unique Identifiers](https://www.nlm.nih.gov/research/umls/new\_users/online\_learning/Meta\_005.html))
* `umls_aui` (_List:_ this concept's [Unified Medical Language System](https://www.nlm.nih.gov/research/umls/index.html) [Atom Unique Identifiers](https://www.nlm.nih.gov/research/umls/new\_users/online\_learning/Meta\_005.html))
* `wikidata` (_String:_ this concept's [Wikidata ID](https://www.wikidata.org/wiki/Wikidata:Identifiers). Same as [`Concept.wikidata`](concept-object.md#wikidata))
* `wikipedia` (_String:_ this concept's Wikipedia page URL)

{% hint style="info" %}
Many concepts are missing one or more ID types (either because we don't know the ID, or because it was never assigned). Keys for null IDs are not displayed..
{% endhint %}

```json
ids: {
    openalex: "https://openalex.org/C2778407487",
    wikidata: "https://www.wikidata.org/wiki/Q14565201",
    wikipedia: "https://en.wikipedia.org/wiki/Altmetrics",
    mag: 2778407487
}
```

### `image_thumbnail_url`

_String:_ Same as [`image_url`](concept-object.md#image\_url), but it's a smaller image.

```json
image_thumbnail_url: "https://upload.wikimedia.org/wikipedia/commons/thumb/f/f1/Altmetrics.svg/100px-Altmetrics.svg.png"
```

### `image_url`

_String:_ URL where you can get an image representing this concept, where available. Usually this is hosted on Wikipedia.

```json
image_url: "https://upload.wikimedia.org/wikipedia/commons/f/f1/Altmetrics.svg"
```

### `international`

_Object:_ This concept's display name in many languages, derived from article titles on each language's wikipedia. See the [Wikidata entry](https://www.wikidata.org/wiki/Q137496#sitelinks-wikipedia) for "Java Bytecode" for example source data.

* `display_name` (_Object_)
  * `key` (String): language code in [wikidata language code](https://www.wikidata.org/wiki/Property:P9753) format. Full list of languages is [here](https://doc.wikimedia.org/mediawiki-core/master/php/Names\_8php\_source.html).
  * `value` (String): `display_name` in the given language

```json
international: {
    display_name: {
        ca: "Altmetrics",
        ...
    }
}
```

### `level`

_Integer:_ The level in the concept tree where this concept lives. Lower-level concepts are more general, and higher-level concepts are more specific. [Computer Science](https://openalex.org/C41008148) has a level of 0; [Java Bytecode](https://openalex.org/C2777472213) has a level of 5. Level 0 concepts have no ancestors and level 5 concepts have no descendants.

```json
level: 2
```

### `related_concepts`

_List:_ Concepts that are similar to this one. Each listed concept is a [dehydrated Concept](concept-object.md#the-dehydratedconcept-object) object, with one additional attribute:

* `score` (_Float_): The strength of association between this concept and the listed concept, on a scale of 0-100.

```json
related_concepts: [
    {
        id: "https://openalex.org/C2778793908",
        wikidata: null,
        display_name: "Citation impact",
        level: 3,
        score: 4.56749
    },
    {
        id: "https://openalex.org/C2779455604",
        wikidata: null,
        display_name: "Impact factor",
        level: 2,
        score: 4.46396
    }
    
    // and so forth
]
```

### `summary_stats`

_Object:_ Citation metrics for this concept

* `2yr_mean_citedness` _Float_: The 2-year mean citedness for this source. Also known as [impact factor](https://en.wikipedia.org/wiki/Impact\_factor). We use the year prior to the current year for the citations (the numerator) and the two years prior to that for the citation-receiving publications (the denominator).
* `h_index` _Integer_: The [_h_-index](https://en.wikipedia.org/wiki/H-index) for this concept.
* `i10_index` _Integer_: The [i-10 index](https://en.wikipedia.org/wiki/Author-level\_metrics#i-10-index) for this concept.

While the _h_-index and the i-10 index are normally author-level metrics and the 2-year mean citedness is normally a journal-level metric, they can be calculated for any set of papers, so we include them for concepts.

```json
summary_stats: {
    2yr_mean_citedness: 1.5295340589458237,
    h_index: 105,
    i10_index: 5045
}
```

### `updated_date`

_String:_ The last time anything in this concept object changed, expressed as an [ISO 8601](https://en.wikipedia.org/wiki/ISO\_8601) date string. This date is updated for _any change at all_, including increases in various counts.

```json
updated_date: "2021-12-25T14:04:30.578837"
```

### `wikidata`

_String:_ The [Wikidata ID](https://www.wikidata.org/wiki/Wikidata:Identifiers) for this concept. This is the [Canonical External ID](../../how-to-use-the-api/get-single-entities/#canonical-external-ids) for concepts.

{% hint style="info" %}
_All_ OpenAlex concepts have a Wikidata ID, because all OpenAlex concepts are also Wikidata concepts.
{% endhint %}

```json
wikidata: "https://www.wikidata.org/wiki/Q14565201"
```

### `works_api_url`

_String:_ An URL that will get you a list of all the works tagged with this concept.

We express this as an API URL (instead of just listing the works themselves) because there might be millions of works tagged with this concept, and that's too many to fit here.

```json
works_api_url: "https://api.openalex.org/works?filter=concept.id:C2778407487"
```

### `works_count`

_Integer:_ The number of works tagged with this concept.

```json
works_count: 3078 
```

## The `DehydratedConcept` object

The `DehydratedConcept` is stripped-down [`Concept`](concept-object.md#the-concept-object) object, with most of its properties removed to save weight. Its only remaining properties are:

* ``[`display_name`](concept-object.md#display\_name)``
* ``[`id`](concept-object.md#id)``
* ``[`level`](concept-object.md#level)``
* ``[`wikidata`](concept-object.md#wikidata)``
