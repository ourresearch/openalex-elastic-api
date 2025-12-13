# Aboutness endpoint (/text)

You can use the `/text` API endpoint to tag your own free text with OpenAlex's "aboutness" assignments—topics, keywords, and concepts.

Accepts a `title` and optional `abstract` in the GET params or as a POST request. The results are straight from the model, with 0 values truncated.

#### Examples

* Get OpenAlex [Keywords](./keywords/README.md) for your text\
  [`https://api.openalex.org/text/keywords?title=type%201%20diabetes%20research%20for%20children`](https://api.openalex.org/text/keywords?title=type%201%20diabetes%20research%20for%20children)
* Get OpenAlex [Topics](./topics/README.md) for your text\
  [`https://api.openalex.org/text/topics?title=type%201%20diabetes%20research%20for%20children`](https://api.openalex.org/text/topics?title=type%201%20diabetes%20research%20for%20children)
* Get OpenAlex [Concepts](./concepts/README.md) for your text\
  [`https://api.openalex.org/text/concepts?title=type%201%20diabetes%20research%20for%20children`](https://api.openalex.org/text/concepts?title=type%201%20diabetes%20research%20for%20children)
* Get all of the above in one request\
  [`https://api.openalex.org/text?title=type%201%20diabetes%20research%20for%20children`](https://api.openalex.org/text?title=type%201%20diabetes%20research%20for%20children)

Example response for that last one:

```json
{
	meta: {
		keywords_count: 5,
		topics_count: 3,
		concepts_count: 3
	},
	keywords: [
		id: "https://openalex.org/keywords/type-1-diabetes",
		display_name: "Type 1 Diabetes",
		score: 0.677
	], ...
	primary_topic: {
		id: "https://openalex.org/T10560",
		display_name: "Management of Diabetes Mellitus and Hypoglycemia",
		score: 0.995
		// more information about the primary topic, removed for brevity
	},
	topics: [
		// list of topic objects with scores
	],
	concepts: [
		// list of concept objects with scores
	]
}
```

Queries are limited to between 20 and 2000 characters. The endpoints are rate limited to 1 per second and 1000 requests per day.
