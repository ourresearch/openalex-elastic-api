# API Overview

The API is the primary way to get OpenAlex data. It's free and requires no authentication. The API uses a credit-based rate limiting system—free users get 100,000 credits per day. For best performance, [add your email](rate-limits-and-authentication.md#the-polite-pool) to all API requests, like `mailto=example@domain.com`.

## Learn more about the API

* [Get single entities](get-single-entities/)
* [Get lists of entities](get-lists-of-entities/) — Learn how to use [paging](get-lists-of-entities/paging.md), [filtering](get-lists-of-entities/filter-entity-lists.md), and [sorting](get-lists-of-entities/sort-entity-lists.md)
* [Get groups of entities](get-groups-of-entities.md) — Group and count entities in different ways
* [Rate limits and authentication](rate-limits-and-authentication.md) — Learn about joining the [polite pool](rate-limits-and-authentication.md#the-polite-pool)
* [Tutorials ](../additional-help/tutorials.md)— Hands-on examples with code

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
