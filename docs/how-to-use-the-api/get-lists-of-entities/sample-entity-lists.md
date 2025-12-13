# Sample entity lists

You can use `sample` to get a random list of up to 10,000 results.

* Get 100 random works\
  [https://api.openalex.org/works?sample=100\&per-page=100](https://api.openalex.org/works?sample=100\&per-page=100)
* Get 50 random works that are open access and published in 2021\
  [https://api.openalex.org/works?filter=open\_access.is\_oa:true,publication\_year:2021\&sample=50\&per-page=50](https://api.openalex.org/works?filter=open\_access.is\_oa:true,publication\_year:2021\&sample=50\&per-page=50)

You can add a `seed` value in order to retrieve the same set of random records, in the same order, multiple times.

* Get 20 random sources with a seed value\
  [https://api.openalex.org/sources?sample=20\&seed=123](https://api.openalex.org/sources?sample=20\&seed=123)

{% hint style="info" %}
Depending on your query, random results with a seed value _may_ change over time due to new records coming into OpenAlex.&#x20;
{% endhint %}

## Limitations

* The sample size is limited to 10,000 results.
* You must provide a `seed` value when paging beyond the first page of results. Without a seed value, you might get duplicate records in your results.
* &#x20;You must use [basic paging](paging.md#basic-paging) when sampling. Cursor pagination is not supported.
