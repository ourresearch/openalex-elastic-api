# Known issues

OpenAlex is still very new, and so you'll encounter some bugs as you look through the data. This page documents the ones we currently know about.&#x20;

{% hint style="info" %}
&#x20;Please report any other issues you find by emailing us at **support@openalex.org**
{% endhint %}

## Questionable dates

Some dates, notably publication dates, come from external sources like publishers and are included in OpenAlex as-is. Dates in the future can be especially suspect.&#x20;

[https://openalex.org/W4205467938](https://openalex.org/W4205467938) has a publication date of 2023-01-31, for example (if you're reading this after February 2023, that date used to be in the future). This date came from publisher-submitted [Crossref metadata](https://api.crossref.org/v1/works/10.1145/3485132) for this article. Looking at [https://dl.acm.org/doi/10.1145/3485132](https://dl.acm.org/doi/10.1145/3485132), this does seem to be part of an ACM issue-in-progress with a print publication date of 2023-01-31.

[https://openalex.org/W4200151376](https://openalex.org/W4200151376) has a publication date in _2029_. This also comes from the publisher's [Crossref metadata](https://api.crossref.org/v1/works/10.12960/tsh.2020.0006), but it's less plausible that the journal has an issue planned that far in advance. On [https://doi.org/10.12960/tsh.2020.0006](https://doi.org/10.12960/tsh.2020.0006), we see an accepted date of 2019-12-21 and a publication date of 2029-01-31, suggesting that the latter is a typo and the _publication\_date_ is wrong.&#x20;

