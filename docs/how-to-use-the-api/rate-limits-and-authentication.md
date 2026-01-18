# Rate limits and authentication

The API uses a credit-based rate limiting system. Different endpoint types consume different amounts of credits per request.

## Credit costs by endpoint type

| Endpoint Type | Example | Credits per Request |
|---------------|---------|---------------------|
| Singleton | `/works/W123`, `/works/W123/ngrams` | 1 |
| List | `/works?filter=...`, `/autocomplete/works` | 10 |
| Content | PDF downloads (future) | 100 |
| Vector | Vector searches (future) | 1,000 |
| Text (Aboutness) | `/text/topics?title=...` | 1,000 |

## Rate limits

The limits are:

* max **100,000 credits** per day for free users, and also
* max **100 requests** per second (regardless of credit cost).

For example, with 100,000 credits you can make:
- 100,000 singleton requests (like `/works/W123`), or
- 10,000 list requests (like `/works?filter=type:article`), or
- Any combination that adds up to 100,000 credits

If you exceed your daily credits or make more than 100 requests per second, you'll get `429` errors instead of useful data.

Are those rate limits too low for you? No problem! We can raise those limits as high as you need if you subscribe to [our Premium plan](https://openalex.org/pricing). Premium users get significantly more credits per day. And if you're an academic researcher we can likely help you out for free; just drop us a line at [support@openalex.org](mailto:support@openalex.org).

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

## The polite pool

The OpenAlex API doesn't require authentication. However, it is helpful for us to know who's behind each API call, for two reasons:

* It allows us to get in touch with the user if something's gone wrong--for instance, their script has run amok and we've needed to start blocking or throttling their usage.
* It lets us report back to our funders, which helps us keep the lights on.

Like Crossref (whose approach we are shamelessly stealing), we separate API users into two pools, the polite pool and the common pool. The polite pool has more consistent response times. It's where you want to be.

To get into the polite pool, you just have to give us an email where we can contact you. You can give us this email in one of two ways:

* Add the `mailto=you@example.com` parameter in your API request, like this: [`https://api.openalex.org/works?mailto=you@example.com`](https://api.openalex.org/works?mailto=you@example.com)
* Add `mailto:you@example.com` somewhere in your User-Agent request header.

## Authentication

You don't need an API key to use OpenAlex. However, [premium users](https://help.openalex.org/hc/en-us/articles/24397762024087-Pricing) do get an API key, which grants higher API limits and enables the use of special filters like [`from_updated_date`](../api-entities/works/filter-works.md#from_updated_date). Using the API key is simple; just add it to your URL using the api\_key param.

* Get a list of all works, using the api key 424242:\
  [`https://api.openalex.org/works?api_key=424242`](https://api.openalex.org/works?api_key=424242)



## Usage tips

### Calling the API in your browser

Because the API is all GET requests without fancy authentication, you can view any request in your browser. This is a very useful and pleasant way to explore the API and debug scripts; we use it all the time.

However, this is _much_ nicer if you install an extension to pretty-print the JSON; [JSONVue (Chrome)](https://chrome.google.com/webstore/detail/jsonvue/chklaanhfefbnpoihckbnefhakgolnmc) and [JSONView (Firefox)](https://addons.mozilla.org/en-US/firefox/addon/jsonview) are popular, free choices. Here's what an API response looks like with one of these extensions enabled:

![A lot prettier than cURL](https://i.imgur.com/E7mNLph.png)
