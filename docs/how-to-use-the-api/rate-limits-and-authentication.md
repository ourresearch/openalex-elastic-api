# Rate limits and authentication

The API uses a credit-based rate limiting system. Different endpoint types consume different amounts of credits per request.

## Credit costs by endpoint type

| Endpoint Type | Example | Credits per Request |
|---------------|---------|---------------------|
| Singleton | `/works/W123`, `/works/W123/ngrams` | 1 |
| List | `/works?filter=...`, `/autocomplete/works` | 10 |
| Content | [`content.openalex.org/works/{id}.pdf`](get-content.md) | 100 |
| Vector | Vector searches (future) | 1,000 |
| Text (Aboutness) | `/text/topics?title=...` | 1,000 |

### High-cost endpoints

Some endpoints consume significantly more credits than standard queries:

| Endpoint | Credits | Daily limit (free) | Notes |
|----------|---------|-------------------|-------|
| [Content downloads](get-content.md) | 100 | \~1,000 files | PDF or GROBID XML |
| Aboutness (`/text`) | 1,000 | \~100 requests | Topic classification |
| Vector search | 1,000 | \~100 requests | Coming soon |

{% hint style="warning" %}
**Planning bulk content downloads?** Downloading all 60M available PDFs would require 6 billion credits. [Contact us](mailto:steve@ourresearch.org) about enterprise credit packs for large-scale projects.
{% endhint %}

## Rate limits

{% hint style="warning" %}
**Starting February 13, 2026, an API key is required** to use the OpenAlex API. API keys are free—[get yours here](https://openalex.org/settings/api). See the [announcement](https://groups.google.com/g/openalex-users/c/rI1GIAySpVQ) for details.
{% endhint %}

The limits are:

* **Without an API key:** 100 credits per day (for testing and demos only)
* **With a free API key:** 100,000 credits per day
* **All users:** max 100 requests per second (regardless of credit cost)

For example, with 100,000 credits you can make:
- 100,000 singleton requests (like `/works/W123`), or
- 10,000 list requests (like `/works?filter=type:article`), or
- Any combination that adds up to 100,000 credits

If you exceed your daily credits or make more than 100 requests per second, you'll get `429` errors instead of useful data.

Need higher limits? Subscribe to [OpenAlex Premium](https://openalex.org/pricing) for significantly more credits per day. Academic researchers can often get increased limits for free—contact [support@openalex.org](mailto:support@openalex.org).

{% hint style="info" %}
Are you scrolling through a list of entities, calling the API for each? You can go way faster by squishing 50 requests into one using our [OR syntax](get-lists-of-entities/filter-entity-lists.md#addition-or). Here's [a tutorial](https://blog.ourresearch.org/fetch-multiple-dois-in-one-openalex-api-request/) showing how.
{% endhint %}

## Rate limit headers

Every API response includes headers showing your current rate limit status:

| Header | Description |
|--------|-------------|
| `X-RateLimit-Limit` | Your total daily credit limit |
| `X-RateLimit-Remaining` | Credits remaining for today |
| `X-RateLimit-Credits-Used` | Credits consumed by this request |
| `X-RateLimit-Reset` | Seconds until your credits reset (midnight UTC) |

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
    "credits_limit": 100000,
    "credits_used": 1234,
    "credits_remaining": 98766,
    "resets_at": "2024-01-02T00:00:00.000Z",
    "resets_in_seconds": 43200,
    "credit_costs": {
      "singleton": 1,
      "list": 10,
      "content": 100,
      "vector": 1000,
      "text": 1000
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

Without an API key, you're limited to just 100 credits per day—enough for quick tests, but not for real work. With a free API key, you get 100,000 credits per day.

[Premium users](https://openalex.org/pricing) get even higher limits and access to special filters like [`from_updated_date`](../api-entities/works/filter-works.md#from_updated_date).



## Usage tips

### Calling the API in your browser

Because the API is all GET requests without fancy authentication, you can view any request in your browser. This is a very useful and pleasant way to explore the API and debug scripts; we use it all the time.

However, this is _much_ nicer if you install an extension to pretty-print the JSON; [JSONVue (Chrome)](https://chrome.google.com/webstore/detail/jsonvue/chklaanhfefbnpoihckbnefhakgolnmc) and [JSONView (Firefox)](https://addons.mozilla.org/en-US/firefox/addon/jsonview) are popular, free choices. Here's what an API response looks like with one of these extensions enabled:

![A lot prettier than cURL](https://i.imgur.com/E7mNLph.png)
