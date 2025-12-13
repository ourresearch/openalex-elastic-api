# Source object

These are the fields in a source object. When you use the API to get a single source or lists of sources, this is what's returned.

### abbreviated\_title

_String:_ An abbreviated title obtained from the [ISSN Centre](https://issn.org).

```json
abbreviated_title: "J. addict. med. ther. sci."
```

### alternate\_titles

_Array:_ Alternate titles for this source, as obtained from the [ISSN Centre](https://issn.org) and individual work records, like Crossref DOIs, that carry the source name as a string. These are commonly abbreviations or translations of the source's canonical name.

```json
alternate_titles: [
   "ACRJ"
]
```

### apc\_prices

_List:_ List of objects, each with `price` (_Integer_) and `currency` (_String_).

Article processing charge information, taken directly from [DOAJ](https://doaj.org/).

```json
apc_prices: [
    {
        price: 3920,
        currency: "GBP"
    }
]
```

### apc\_usd

_Integer:_ The source's article processing charge in US Dollars, if available from [DOAJ](https://doaj.org/).

The `apc_usd` value is calculated by taking the APC price (see [`apc_prices`](source-object.md#apc\_prices)) with a currency of USD if it is available. If it's not available, we convert the first available value from `apc_prices` into USD, using recent exchange rates.

```json
apc_usd: 5200
```

### `cited_by_count`

_Integer:_ The total number of [`Works`](../works/work-object/) that cite a `Work` hosted in this source.

```json
cited_by_count: 133702 
```

### `country_code`

_String:_ The country that this source is associated with, represented as an [ISO two-letter country code](https://en.wikipedia.org/wiki/ISO\_3166-1\_alpha-2).

```json
country_code: "GB" 
```

### `counts_by_year`

_List:_ [`works_count`](source-object.md#works\_count) and [`cited_by_count`](source-object.md#cited\_by\_count) for each of the last ten years, binned by year. To put it another way: each year, you can see how many new works this source started hosting, and how many times _any_ work in this source got cited.

If the source was founded less than ten years ago, there will naturally be fewer than ten years in this list. Years with zero citations and zero works have been removed so you will need to add those in if you need them.

```json
counts_by_year: [
    {
        year: 2021,
        works_count: 4338,
        cited_by_count: 127268
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

_String:_ The date this `Source` object was created in the OpenAlex dataset, expressed as an [ISO 8601](https://en.wikipedia.org/wiki/ISO\_8601) date string.

```json
created_date: "2017-08-08"
```

### `display_name`

_String:_ The name of the source.

```json
display_name: "PeerJ"
```

### `homepage_url`

_String:_ The starting page for navigating the contents of this source; the homepage for this source's website.

```json
homepage_url: "http://www.peerj.com/" 
```

### `host_organization`

_String:_ The host organization for this source as an [OpenAlex ID](../../how-to-use-the-api/get-single-entities/#the-openalex-id). This will be an [`Institution.id`](../institutions/institution-object.md#id) if the source is a repository, and a [`Publisher.id`](../publishers/publisher-object.md#id) if the source is a journal, conference, or eBook platform (based on the [`type`](source-object.md#type) field).

```json
id: "https://openalex.org/P4310320595"
```

### `host_organization_lineage`

_List:_ [OpenAlex IDs](../../how-to-use-the-api/get-single-entities/#the-openalex-id) — See [`Publisher.lineage`](../publishers/publisher-object.md#lineage). This will only be included if the [`host_organization`](source-object.md#host\_organization) is a publisher (and not if the `host_organization` is an institution).

```json
host_organization_lineage: [
    "https://openalex.org/P4310321285",
    "https://openalex.org/P4310319900",
    "https://openalex.org/P4310319965"
]
```

### `host_organization_name`

_String:_ The `display_name` from the [host\_organization](source-object.md#host\_organization), shown for convenience.

```json
host_organization_name: "Elsevier BV" 
```

### `id`

_String:_ The [OpenAlex ID](../../how-to-use-the-api/get-single-entities/#the-openalex-id) for this source.

```json
id: "https://openalex.org/S1983995261"
```

### `ids`

_Object:_ All the external identifiers that we know about for this source. IDs are expressed as URIs whenever possible. Possible ID types:

* `fatcat` (_String_: this source's [Fatcat](https://fatcat.wiki/) ID)
* `issn` (_List:_ a list of this source's ISSNs. Same as [`Source.issn`](source-object.md#issn))
* `issn_l` (_String:_ this source's ISSN-L. Same as [`Source.issn_l`](source-object.md#issn\_l))
* `mag` (_Integer:_ this source's [Microsoft Academic Graph](https://www.microsoft.com/en-us/research/project/microsoft-academic-graph/) ID)
* `openalex` (_String:_ this source's [OpenAlex ID](../../how-to-use-the-api/get-single-entities/#the-openalex-id). Same as [`Source.id`](source-object.md#id))
* `wikidata` (_String_: this source's [Wikidata](https://www.wikidata.org/wiki/Wikidata:Main\_Page) ID)

{% hint style="info" %}
Many sources are missing one or more ID types (either because we don't know the ID, or because it was never assigned). Keys for null IDs are not displayed.
{% endhint %}

<details>

<summary>Example</summary>

{% code fullWidth="true" %}
```json
ids: {
    openalex: "https://openalex.org/S1983995261",
    issn_l: "2167-8359",
    issn: [
        "2167-8359"
    ],
    mag: 1983995261,
    fatcat: "https://fatcat.wiki/container/z3ijzhu7zzey3f7jwws7rzopoq",
    wikidata: "https://www.wikidata.org/entity/Q96326029"
}
```
{% endcode %}

</details>

### `is_core`

_Boolean:_ Whether this source is identified as a "core source" by [CWTS](https://www.cwts.nl/), used in the [Open Leiden Ranking](https://open.leidenranking.com/) of universities around the world. The list of core sources can be found [here](https://zenodo.org/records/10949671).

```json
is_core: true 
```

### `is_in_doaj`

_Boolean:_ Whether this is a journal listed in the [Directory of Open Access Journals](https://doaj.org/) (DOAJ).

```json
is_in_doaj: true 
```

### `is_oa`

_Boolean:_ Whether this is currently fully-open-access source. This could be `true` for a preprint repository where everything uploaded is free to read, or for a [Gold](https://en.wikipedia.org/wiki/Open\_access#Colour\_naming\_system) or [Diamond](https://en.wikipedia.org/wiki/Diamond\_open\_access) open access journal, where all newly published Works are available for free under an open license.

We say "currently" because the status of a source can change over time. It's common for journals to "flip" to Gold OA, after which they may make only future articles open or also open their back catalogs. It's entirely possible for a source to say `is_oa: true`, but for an article from last year to require a subscription.

```json
is_oa: true 
```

### `issn`

_List:_ The [ISSNs](https://en.wikipedia.org/wiki/International\_Standard\_Serial\_Number) used by this source. Many publications have multiple ISSNs , so [ISSN-L](source-object.md#issn\_l) should be used when possible.

```json
issn: ["2167-8359"]
```

### `issn_l`

_String:_ The [ISSN-L](https://en.wikipedia.org/wiki/International\_Standard\_Serial\_Number#Linking\_ISSN) identifying this source. This is the [Canonical External ID](../../how-to-use-the-api/get-single-entities/#canonical-external-ids) for sources.

ISSN is a global and unique ID for serial publications. However, different media versions of a given publication (e.g., print and electronic) often have _different_ ISSNs. This is why we can't have nice things. The ISSN-L or Linking ISSN solves the problem by designating a single canonical ISSN for all media versions of the title. It's _usually_ the same as the print ISSN.

```json
issn_l: "2167-8359"
```

### societies

_Array:_ Societies on whose behalf the source is published and maintained, obtained from our [crowdsourced list](https://blog.ourresearch.org/society-list/). Thanks!

```json
societies: [
    {
        "url": "http://www.counseling.org/",
        "organization": "American Counseling Association on behalf of the American College Counseling Association"
    }
]
```

### `summary_stats`

_Object:_ Citation metrics for this source

* `2yr_mean_citedness` _Float_: The 2-year mean citedness for this source. Also known as [impact factor](https://en.wikipedia.org/wiki/Impact\_factor). We use the year prior to the current year for the citations (the numerator) and the two years prior to that for the citation-receiving publications (the denominator).
* `h_index` _Integer_: The [_h_-index](https://en.wikipedia.org/wiki/H-index) for this source.
* `i10_index` _Integer_: The [i-10 index](https://en.wikipedia.org/wiki/Author-level\_metrics#i-10-index) for this source.

While the _h_-index and the i-10 index are normally author-level metrics, they can be calculated for any set of papers, so we include them for sources.

```json
summary_stats: {
    2yr_mean_citedness: 1.5295340589458237,
    h_index: 105,
    i10_index: 5045
}
```

### `type`

_String:_ The type of source, which will be one of: `journal`, `repository`, `conference`, `ebook platform`, `book series`, `metadata`, or `other`.

```json
type: "journal" 
```

### `updated_date`

_String:_ The last time anything in this `Source` object changed, expressed as an [ISO 8601](https://en.wikipedia.org/wiki/ISO\_8601) date string. This date is updated for _any change at all_, including increases in various counts.

```json
updated_date: "2022-01-02T00:00:00"
```

### `works_api_url`

_String:_ A URL that will get you a list of all this source's `Works`.

We express this as an API URL (instead of just listing the works themselves) because sometimes a source's publication list is too long to reasonably fit into a single `Source` object.

```json
works_api_url: "https://api.openalex.org/works?filter=primary_location.source.id:S1983995261",
```

### `works_count`

_Integer:_ The number of [`Works`](../works/work-object/) this source hosts.

```json
works_count: 20184 
```

### `x_concepts`

{% hint style="danger" %}
`x_concepts` will be deprecated and removed soon. We will be replacing this functionality with [`Topics`](../topics/README.md) instead.
{% endhint %}

_List:_ The `Concepts` most frequently applied to works hosted by this source. Each is represented as a [dehydrated Concept](../concepts/concept-object.md#the-dehydratedconcept-object) object, with one additional attribute:

`score` (_Float_): The strength of association between this source and the listed concept, from 0-100.

```json
x_concepts: [
    {
        id: "https://openalex.org/C86803240",
        wikidata: null,
        display_name: "Biology",
        level: 0,
        score: 86.7
    },
    {
        id: "https://openalex.org/C185592680",
        wikidata: null,
        display_name: "Chemistry",
        level: 0,
        score: 51.4
    },
    
    // and so forth
]
```

## The `DehydratedSource` object

The `DehydratedSource` is stripped-down `Source` object, with most of its properties removed to save weight. Its only remaining properties are:

* [`display_name`](source-object.md#display\_name)
* [`host_organization`](source-object.md#host\_organization)
* [`host_organization_lineage`](source-object.md#host\_organization\_lineage)
* [`host_organization_name`](source-object.md#host\_organization\_name)
* [`id`](source-object.md#id)
* [`is_core`](#is_core)
* [`is_in_doaj`](source-object.md#is\_in\_doaj)
* [`is_oa`](source-object.md#is\_oa)
* [`issn`](source-object.md#issn)
* [`issn_l`](source-object.md#issn\_l)
* [`type`](source-object.md#type)
