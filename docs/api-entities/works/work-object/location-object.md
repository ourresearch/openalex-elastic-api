# Location object

The `Location` object describes the location of a given work. It's only found as part of the `Work` object.

Locations are meant to capture the way that a work exists in different versions. So, for example, a work may have a version that has been peer-reviewed and published in a journal (the [version of record](https://en.wikipedia.org/wiki/Version_of_record)). This would be one of the work's locations. It may have another version available on a preprint server like [bioRxiv](https://www.biorxiv.org/)—this version having been posted before it was accepted for publication. This would be another one of the work's locations.

Below is an example of a work in OpenAlex ([https://openalex.org/W2807749226](https://openalex.org/W2807749226)) that has multiple locations with different properties. The version of record, published in a peer-reviewed journal, is listed first, and is not open-access. The second location is a university repository, where one can find an open-access copy of the published version of the work. Other locations are listed below.

<figure><img src="../../../.gitbook/assets/locations_screenshot_annotate (3).png" alt=""><figcaption><p>One work can have multiple locations. These locations can differ in properties such as version and open-access status.</p></figcaption></figure>

Locations are meant to cover anywhere that a given work can be found. This can include journals, proceedings, institutional repositories, and subject-area repositories like [arXiv ](https://arxiv.org/)and [bioRxiv](https://www.biorxiv.org/). If you are only interested in a certain one of these (like journal), you can use a [filter](../filter-works.md) to specify the `locations.source.type`. ([Learn more about types here.](../../sources/source-object.md#type))

There are three places in the `Work` object where you can find locations:

* [`primary_location`](./#primary_location): The best (closest to the [version of record](https://en.wikipedia.org/wiki/Version_of_record)) copy of this work.
* [`best_oa_location`](./#best_oa_location): The best available open access location of this work.
* [`locations`](./#locations): A list of all of the locations where this work lives. This will include the two locations above if availabe, and can also include other locations.

### `is_accepted`

_Boolean:_ `true` if this location's [`version`](location-object.md#version) is either `acceptedVersion` or `publishedVersion`; otherwise `false`.

```json
is_accepted: true
```

### `is_oa`

_Boolean:_ `True` if an Open Access (OA) version of this work is available at this location.

There are [many ways to define OA](https://peerj.com/articles/4375/#literature-review). OpenAlex uses a broad definition: having a URL where you can read the fulltext of this work without needing to pay money or log in.

```json
is_oa: true
```

### `is_published`

_Boolean:_ `true` if this location's [`version`](location-object.md#version) is `publishedVersion`; otherwise `false`.

```json
is_published: true
```

### landing\_page\_url

_String:_ The landing page URL for this location.

```json
landing_page_url: "https://doi.org/10.1590/s1678-77572010000100010"
```

### license

_String:_ The location's publishing license. This can be a [Creative Commons](https://creativecommons.org/about/cclicenses/) license such as cc0 or cc-by, a publisher-specific license, or null which means we are not able to determine a license for this location.

```json
license: "cc-by"
```

### source

_Object:_ Information about the source of this location, as a [`DehydratedSource`](../../sources/source-object.md#the-dehydratedsource-object) object.

The concept of a source is meant to capture a certain social relationship between the host organization and a version of a work. When an organization puts the work on the internet, there is an understanding that they have, at some level, endorsed the work. This level varies, and can be very different depending on the source!

```json
source {
    id: "https://openalex.org/S125754415",
    display_name: "Proceedings of the National Academy of Sciences of the United States of America",
    issn_l: "0027-8424",
    issn: ["1091-6490", "0027-8424"],
    host_organization: "https://openalex.org/P4310320052",
    type: "journal"
}
```

### pdf\_url

_String:_ A URL where you can find this location as a PDF.

```json
pdf_url: "http://www.scielo.br/pdf/jaos/v18n1/a10v18n1.pdf"
```

### version

_String:_ The version of the work, based on the [DRIVER Guidelines versioning scheme.](https://wiki.surfnet.nl/display/DRIVERguidelines/DRIVER-VERSION+Mappings) Possible values are:.

* `publishedVersion`: The document’s version of record. This is the most authoritative version.
* `acceptedVersion`: The document after having completed peer review and being officially accepted for publication. It will lack publisher formatting, but the _content_ should be interchangeable with the that of the `publishedVersion`.
* `submittedVersion`: the document as submitted to the publisher by the authors, but _before_ peer-review. Its content may differ significantly from that of the accepted article.

```json
version: "publishedVersion"
```

### raw\_type

_String:_ The type, _according to this location's source_. This uses whatever controlled vocabulary that source happens to fancy. So for example: if the location is from from Crossref, you'll see a term from [the Crossref type vocabulary](https://api.crossref.org/types) in the `location.raw_type` field.

```json
raw_type: "journal-article"
```
