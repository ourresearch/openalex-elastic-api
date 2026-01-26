---
description: Access 190M+ new works in OpenAlex
---

# XPAC

On November 4, 2025, we added over 190 million new works to OpenAlex as part of [a rewrite codenamed Walden](https://blog.openalex.org/openalex-rewrite-walden-launch/). This expansion pack (XPAC for short) includes all of DataCite, plus thousands of institutional and subject-area repositories.

For more information on XPAC, see the [Walden release notes](https://docs.google.com/document/d/1SPZ7QFcPddCHYt1pZP1UCIuqbfBY22lSHwgPA8RQyUY/edit?tab=t.0).

## Why are XPAC works excluded by default?

The data quality on XPAC works is generally not as high as on other works, but it will improve over time. To avoid surprising users with a sudden change in result counts and quality, XPAC works are **excluded by default** from API results.

## The `include_xpac` parameter

You can include XPAC works in your results by adding the `include_xpac=true` parameter to any works endpoint call:

* Get all works, including those in XPAC:\
  [`https://api.openalex.org/works?include_xpac=true`](https://api.openalex.org/works?include_xpac=true)

Without this parameter, you'll get approximately 278 million works. With `include_xpac=true`, you'll get over 470 million works.

{% hint style="info" %}
The `include_xpac` parameter defaults to `false`. You must explicitly set it to `true` to include XPAC works in your results.
{% endhint %}

## The `is_xpac` field

Each work has an [`is_xpac`](../api-entities/works/work-object/#is_xpac) boolean field that indicates whether it's part of the XPAC dataset. You can also use this as a filter:

* Get only XPAC works:\
  [`https://api.openalex.org/works?include_xpac=true&filter=is_xpac:true`](https://api.openalex.org/works?include_xpac=true&filter=is_xpac:true)
