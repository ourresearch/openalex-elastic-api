---
description: Access 192M new works in OpenAlex
icon: layer-plus
---

# xpac

On November 4, 2025, we added 192M new works to OpenAlex as part of [a rewrite codenamed Walden](https://blog.openalex.org/openalex-rewrite-walden-launch/). This expansion pack (xpac for short) includes all of DataCite, plus thousands of institutional and subject-area repositories.

For more information on xpac, see the [Walden release notes.](https://docs.google.com/document/d/1SPZ7QFcPddCHYt1pZP1UCIuqbfBY22lSHwgPA8RQyUY/edit?tab=t.0)

You can access xpac by adding the `include_xpath=true` parameter to any entity endpoint call.  Here's an example:

* Get all works, including those in xpac:\
  [`https://api.openalex.org/works?include_xpac=true`](https://api.openalex.org/works?include_xpac=true)
