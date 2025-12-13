# Get a single work

It's easy to get a work from from the API with: `/works/<entity_id>` Here's an example:

* Get the work with the [OpenAlex ID](../../how-to-use-the-api/get-single-entities/#the-openalex-id) `W2741809807`: [`https://api.openalex.org/works/W2741809807`](https://api.openalex.org/works/W2741809807)

That will return a [`Work`](work-object/) object, describing everything OpenAlex knows about the work with that ID.

```json
{
    "id": "https://openalex.org/W2741809807",
    "doi": "https://doi.org/10.7717/peerj.4375",
    "title": "The state of OA: a large-scale analysis of the prevalence and impact of Open Access articles",
    "display_name": "The state of OA: a large-scale analysis of the prevalence and impact of Open Access articles",
    "publication_year": 2018,
    "publication_date": "2018-02-13",
    // other fields removed for brevity
}
```

{% hint style="info" %}
You can make up to 50 of these queries at once by requesting a list of entities and filtering on IDs [using OR syntax](../../how-to-use-the-api/get-lists-of-entities/filter-entity-lists.md#addition-or) ([tutorial](https://blog.ourresearch.org/fetch-multiple-dois-in-one-openalex-api-request/)).
{% endhint %}

## External IDs

You can look up works using external IDs such as a DOI:

* Get the work with this DOI: `https://doi.org/10.7717/peerj.4375`:\
  [https://api.openalex.org/works/https://doi.org/10.7717/peerj.4375](https://api.openalex.org/works/https://doi.org/10.7717/peerj.4375)

You can use the full ID or a shorter Uniform Resource Name (URN) format like so:

* Get the work with PubMed ID: `https://pubmed.ncbi.nlm.nih.gov/14907713`:\
  [https://api.openalex.org/works/pmid:14907713](https://api.openalex.org/works/pmid:14907713)

Available external IDs for works are:

| External ID                    | URN     |
| ------------------------------ | ------- |
| DOI                            | `doi`   |
| Microsoft Academic Graph (MAG) | `mag`   |
| PubMed ID (PMID)               | `pmid`  |
| PubMed Central ID (PMCID)      | `pmcid` |

{% hint style="warning" %}
You must make sure that the ID(s) you supply are valid and correct. If an ID you request is incorrect, you will get no result. If you request an illegal ID—such as one containing a `,` or `&`, the query will fail and you will get a 403 error.
{% endhint %}

### Select fields

You can use `select` to limit the fields that are returned in a work object. More details are [here](../../how-to-use-the-api/get-lists-of-entities/select-fields.md).

* Display only the `id` and `display_name` for a work object\
  [https://api.openalex.org/works/W2741809807?select=id,display\_name](https://api.openalex.org/works/W2741809807?select=id,display\_name)
