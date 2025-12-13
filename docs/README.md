# Overview

[**OpenAlex**](https://openalex.org) is a fully open catalog of the global research system. It's named after the [ancient Library of Alexandria](https://en.wikipedia.org/wiki/Library_of_Alexandria) and made by the nonprofit [OurResearch](https://ourresearch.org/).

This is the **technical documentation for OpenAlex,** including the [**OpenAlex API**](how-to-use-the-api/api-overview.md) and the [**data snapshot**](https://docs.openalex.org/download-all-data/openalex-snapshot)**.** Here, you can learn how to set up your code to access OpenAlex's data. If you want to explore the data as a human, you may be more interested in [**OpenAlex Web**](https://help.openalex.org)**.**

## Data

The OpenAlex dataset describes scholarly [_entities_ ](api-entities/entities-overview.md)and how those entities are connected to each other. Types of entities include [works](api-entities/works/), [authors](api-entities/authors/), [sources](api-entities/sources/), [institutions](api-entities/institutions/), [topics](api-entities/topics/), [publishers](api-entities/publishers/), and [funders](api-entities/funders/).

Together, these make a huge web (or more technically, heterogeneous directed [graph](https://en.wikipedia.org/wiki/Graph_theory)) of hundreds of millions of entities and billions of connections between them all.

Learn more at our general help center article: [About the data](https://help.openalex.org/hc/en-us/articles/24397285563671-About-the-data)

## Access

We offer a fast, modern REST API to get OpenAlex data programmatically. It's free and requires no authentication. The daily limit for API calls is 100,000 requests per user per day. For best performance, [add your email](how-to-use-the-api/rate-limits-and-authentication.md#the-polite-pool) to all API requests, like `mailto=example@domain.com`. [Learn more](how-to-use-the-api/api-overview.md)

There is also a complete database snapshot available to download. [Learn more about the data snapshot here.](download-all-data/openalex-snapshot.md)

The API has a limit of 100,000 calls per day, and the snapshot is updated monthly. If you need a higher limit, or more frequent updates, please look into [**OpenAlex Premium.**](https://openalex.org/pricing)

The web interface for OpenAlex, built directly on top of the API, is the quickest and easiest way to [get started with OpenAlex](https://help.openalex.org/getting-started).

## Why OpenAlex?

OpenAlex offers an open replacement for industry-standard scientific knowledge bases like Elsevier's Scopus and Clarivate's Web of Science. [Compared to](https://openalex.org/about#comparison) these paywalled services, OpenAlex offers significant advantages in terms of inclusivity, affordability, and avaliability.

OpenAlex is:

* _Big —_ We have about twice the coverage of the other services, and have significantly better coverage of non-English works and works from the Global South.
* _Easy —_ Our service is fast, modern, and well-documented.
* _Open —_ Our complete dataset is free under the CC0 license, which allows for transparency and reuse.

Many people and organizations have already found great value using OpenAlex. Have a look at the [Testimonials](https://openalex.org/testimonials) to hear what they've said!

## Contact

For tech support and bug reports, please visit our [help page](https://openalex.org/help). You can also join the [OpenAlex user group](https://groups.google.com/g/openalex-users), and follow us on [Twitter (@OpenAlex\_org)](https://twitter.com/openalex_org) and [Mastodon](https://mastodon.social/@OpenAlex).

## Citation

If you use OpenAlex in research, please cite [this paper](https://arxiv.org/abs/2205.01833):

> Priem, J., Piwowar, H., & Orr, R. (2022). _OpenAlex: A fully-open index of scholarly works, authors, venues, institutions, and concepts_. ArXiv. https://arxiv.org/abs/2205.01833
