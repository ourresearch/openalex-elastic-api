# Funder object

The `Funder` object represents a funding organization associated with a work. It is only found as part of a `Work` object, in the [`work.funders`](./#funders) property.

{% hint style="info" %}
The `funders` property, along with [`awards`](./#awards), replaces the older `grants` property which has been removed. These new properties provide much more comprehensive funding data.
{% endhint %}

### `id`

_String:_ The OpenAlex ID for this funder.

```json
id: "https://openalex.org/F4320306076"
```

### `display_name`

_String:_ The name of the funding organization.

```json
display_name: "National Science Foundation"
```

### `ror`

_String:_ The [ROR](https://ror.org/) ID for this funder, if available.

```json
ror: "https://ror.org/021nxhr62"
```
