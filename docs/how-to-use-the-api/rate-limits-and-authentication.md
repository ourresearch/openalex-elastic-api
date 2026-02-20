# Rate limits and authentication

The API uses simple, transparent pricing. Different endpoint types cost different amounts per request.

## Endpoint pricing

| Endpoint Type | Example | Cost per call | Cost per 1,000 calls |
|---------------|---------|--------------|---------------------|
| Singleton | `/works/W123`, `/works/W123/ngrams` | Free | Free |
| List | `/works?filter=...`, `/autocomplete/works` | $0.0001 | $0.10 |
| Search | `/works?search=cancer`, `/works?filter=title.search:...` | $0.001 | $1.00 |
| Semantic | `/works?search.semantic=...` | $0.001 | $1.00 |
| Content | [`content.openalex.org/works/{id}.pdf`](get-content.md) | $0.01 | $10.00 |
| Text (Aboutness) | `/text/topics?title=...` | $0.01 | $10.00 |

### High-cost endpoints

Some endpoints cost significantly more than standard queries:

| Endpoint | Cost per call | Daily limit (free) | Notes |
|----------|--------------|-------------------|-------|
| [Content downloads](get-content.md) | $0.01 | ~100 files | PDF or TEI XML |
| Aboutness (`/text`) | $0.01 | ~100 requests | Topic classification |
| Semantic search | $0.001 | ~1,000 requests | `?search.semantic=` |

{% hint style="warning" %}
**Planning bulk content downloads?** Downloading all 60M available PDFs would cost ~$600,000. [Contact us](mailto:steve@ourresearch.org) about enterprise pricing for large-scale projects.
{% endhint %}

## Rate limits

{% hint style="warning" %}
**Starting February 13, 2026, an API key is required** to use the OpenAlex API. API keys are free—[get yours here](https://openalex.org/settings/api). See the [announcement](https://groups.google.com/g/openalex-users/c/rI1GIAySpVQ) for details.
{% endhint %}

The limits are:

* **Without an API key:** $0.01/day API budget (for testing and demos only)
* **With a free API key:** $1/day API budget
* **All users:** max 100 requests per second (regardless of cost)

For example, with a $1/day budget you can make:
- Unlimited singleton requests (like `/works/W123`) — they're free!
- 10,000 list requests (like `/works?filter=type:article`), or
- Any combination that adds up to $1

If you exceed your daily budget or make more than 100 requests per second, you'll get `429` errors instead of useful data.

Need a higher budget? Subscribe to [OpenAlex Premium](https://openalex.org/pricing) for significantly more. Academic researchers can often get increased limits for free—contact [support@openalex.org](mailto:support@openalex.org).

{% hint style="info" %}
Are you scrolling through a list of entities, calling the API for each? You can go way faster by squishing 50 requests into one using our [OR syntax](get-lists-of-entities/filter-entity-lists.md#addition-or). Here's [a tutorial](https://blog.ourresearch.org/fetch-multiple-dois-in-one-openalex-api-request/) showing how.
{% endhint %}

## Rate limit headers

Every API response includes headers showing your current rate limit status:

| Header | Description |
|--------|-------------|
| `X-RateLimit-Limit-USD` | Your total daily API budget in USD |
| `X-RateLimit-Remaining-USD` | Budget remaining for today in USD |
| `X-RateLimit-Cost-USD` | Cost of this request in USD |
| `X-RateLimit-Prepaid-Remaining-USD` | Prepaid balance remaining in USD |
| `X-RateLimit-Reset` | Seconds until your budget resets (midnight UTC) |

## Check your rate limit status

You can check your current rate limit status at any time using the `/rate-limit` endpoint (requires an API key):

```
GET https://api.openalex.org/rate-limit?api_key=YOUR_API_KEY
```

Response:
```json
{
  "api_key": "abc...xyz",
  "rate_limit": {
    "daily_budget_usd": 1.0,
    "daily_used_usd": 0.1234,
    "daily_remaining_usd": 0.8766,
    "prepaid_balance_usd": 0,
    "prepaid_remaining_usd": 0,
    "prepaid_expires_at": null,
    "resets_at": "2026-02-19T00:00:00.000Z",
    "resets_in_seconds": 43200,
    "endpoint_costs_usd": {
      "singleton": 0,
      "list": 0.0001,
      "search": 0.001,
      "semantic": 0.001,
      "content": 0.01,
      "text": 0.01
    }
  }
}
```

## Authentication

An API key is required to use the OpenAlex API. The good news: API keys are free! Here's how to get one:

1. Create a free account at [openalex.org](https://openalex.org)
2. Go to [openalex.org/settings/api](https://openalex.org/settings/api) to get your key
3. Add `api_key=YOUR_KEY` to your API calls

Example:
* [`https://api.openalex.org/works?api_key=YOUR_KEY`](https://api.openalex.org/works?api_key=YOUR_KEY)

Without an API key, you're limited to just $0.01/day—enough for quick tests, but not for real work. With a free API key, you get $1/day of API budget.

[Premium users](https://openalex.org/pricing) get even higher budgets and access to special filters like [`from_updated_date`](../api-entities/works/filter-works.md#from_updated_date).



## Usage tips

### Calling the API in your browser

Because the API is all GET requests without fancy authentication, you can view any request in your browser. This is a very useful and pleasant way to explore the API and debug scripts; we use it all the time.

However, this is _much_ nicer if you install an extension to pretty-print the JSON; [JSONVue (Chrome)](https://chrome.google.com/webstore/detail/jsonvue/chklaanhfefbnpoihckbnefhakgolnmc) and [JSONView (Firefox)](https://addons.mozilla.org/en-US/firefox/addon/jsonview) are popular, free choices. Here's what an API response looks like with one of these extensions enabled:

![A lot prettier than cURL](https://i.imgur.com/E7mNLph.png)
