# API Overview

The API is the primary way to get OpenAlex data. It's free but requires an API key (also free). Get yours at [openalex.org/settings/api](https://openalex.org/settings/api). With your free key, you get $1/day of API budget.

## Learn more about the API

OpenAlex offers four service types, each optimized for different use cases:

* [Get single entities](get-single-entities/)
* [Get lists of entities](get-lists-of-entities/) — Learn how to use [paging](get-lists-of-entities/paging.md), [filtering](get-lists-of-entities/filter-entity-lists.md), and [sorting](get-lists-of-entities/sort-entity-lists.md)
  * [Get groups of entities](get-groups-of-entities.md) — Group and count entities in different ways
* [Find similar works](find-similar-works.md) — AI-powered semantic search
* [Get content](get-content.md) — Download PDFs and TEI XML

{% hint style="info" %}
Each service type has a different cost. Single entity lookups are free, list queries cost $0.0001, search queries (including semantic search) cost $0.001, and content downloads cost $0.01 per file. See [Rate limits and authentication](rate-limits-and-authentication.md) for details.
{% endhint %}

See also:
* [Rate limits and authentication](rate-limits-and-authentication.md) — Learn about pricing and API keys
* [Tutorials](../additional-help/tutorials.md) — Hands-on examples with code

## Client Libraries

There are several third-party libraries you can use to get data from OpenAlex:

* [openalexR](https://github.com/ropensci/openalexR) (R)
* [OpenAlex2Pajek](https://github.com/bavla/OpenAlex/tree/main/OpenAlex2Pajek) (R)
* [KtAlex](https://github.com/benedekh/KtAlex) (Kotlin)
* [PyAlex](https://github.com/J535D165/pyalex) (Python)
* [diophila](https://pypi.org/project/diophila/) (Python)
* [OpenAlexAPI](https://pypi.org/project/openalexapi/) (Python)

If you're looking for a visual interface, you can also check out the free [VOSviewer](https://www.vosviewer.com/), which lets you make network visualizations based on OpenAlex data:

![](<../.gitbook/assets/Screenshot by Dropbox Capture (1).png>)
