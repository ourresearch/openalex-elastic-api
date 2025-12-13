# Rate limits and authentication

The API is rate-limited. The limits are:

* max 100,000 calls every day, and also
* max 10 requests every second.

If you hit the API more than 100k times in a day or more than 10 in a second, you'll get `429` errors instead of useful data.

Are those rate limits too low for you? No problem! We can raise those limits as high as you need if you subscribe to [our Premium plan](https://openalex.org/pricing). And if you're an academic researcher we can likely do it for free; just drop us a line at [support@openalex.org](mailto:support@openalex.org).

{% hint style="info" %}
Are you scrolling through a list of entities, calling the API for each? You can go way faster by squishing 50 requests into one using our [OR syntax](get-lists-of-entities/filter-entity-lists.md#addition-or). Here's [a tutorial](https://blog.ourresearch.org/fetch-multiple-dois-in-one-openalex-api-request/) showing how.
{% endhint %}

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
