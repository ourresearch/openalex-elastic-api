# Award object

The `Award` object represents a grant or award associated with a work. It is only found as part of a `Work` object, in the [`work.awards`](./#awards) property.

{% hint style="info" %}
The `awards` property, along with [`funders`](./#funders), replaces the older `grants` property which has been removed. These new properties provide much more comprehensive funding data.
{% endhint %}

### `id`

_String:_ The OpenAlex ID for this award.

```json
id: "https://openalex.org/A4320000001"
```

### `display_name`

_String:_ The name or title of the award.

```json
display_name: "Research Grant for Climate Studies"
```

### `funder_award_id`

_String:_ The award identifier as assigned by the funder (e.g., the grant number).

```json
funder_award_id: "ABI 1661218"
```

### `funder_id`

_String:_ The OpenAlex ID of the [`Funder`](../../funders/) that issued this award.

```json
funder_id: "https://openalex.org/F4320306076"
```

### `funder_display_name`

_String:_ The display name of the funder that issued this award.

```json
funder_display_name: "National Science Foundation"
```

### `doi`

_String:_ The DOI for this award, if available.

```json
doi: "https://doi.org/10.xxxx/award.123"
```
