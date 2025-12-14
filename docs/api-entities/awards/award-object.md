# Award object

These are the fields in an award object. When you use the API to get a single award or lists of awards, this is what's returned.

### `id`

_String:_ The OpenAlex ID for this award.

```json
id: "https://openalex.org/G1929887790"
```

### `display_name`

_String:_ The name or title of the award, if available.

```json
display_name: "Research Grant for Climate Studies"
```

### `description`

_String:_ A description of the award, if available.

```json
description: "Funding for research on climate change impacts"
```

### `funder_award_id`

_String:_ The award identifier as assigned by the funder (e.g., the grant number).

```json
funder_award_id: "ABI 1661218"
```

### `funder`

_Object:_ Information about the funder that issued this award. Contains:

* `id`: _String_ — The OpenAlex ID for the funder
* `display_name`: _String_ — The name of the funder
* `ror`: _String_ — The ROR ID for the funder
* `doi`: _String_ — The DOI for the funder

```json
funder: {
    id: "https://openalex.org/F4320306076",
    display_name: "National Science Foundation",
    ror: "https://ror.org/021nxhr62",
    doi: "https://doi.org/10.13039/100000001"
}
```

### `funded_outputs`

_List:_ A list of OpenAlex Work IDs that were funded by this award.

```json
funded_outputs: [
    "https://openalex.org/W3016825602",
    "https://openalex.org/W2753353163"
]
```

### `funded_outputs_count`

_Integer:_ The number of works funded by this award.

```json
funded_outputs_count: 2
```

### `amount`

_Float:_ The monetary amount of the award, if available.

```json
amount: 500000.00
```

### `currency`

_String:_ The currency of the award amount (e.g., "USD", "EUR"), if available.

```json
currency: "USD"
```

### `funding_type`

_String:_ The type of funding provided (e.g., "grant", "fellowship"), if available.

```json
funding_type: "grant"
```

### `funder_scheme`

_String:_ The specific funding scheme or program under which the award was made, if available.

```json
funder_scheme: "Division of Biological Infrastructure"
```

### `start_date`

_String:_ The start date of the award, formatted as an ISO 8601 date string, if available.

```json
start_date: "2020-01-01"
```

### `end_date`

_String:_ The end date of the award, formatted as an ISO 8601 date string, if available.

```json
end_date: "2023-12-31"
```

### `start_year`

_Integer:_ The year when the award started, if available.

```json
start_year: 2020
```

### `end_year`

_Integer:_ The year when the award ends or ended, if available.

```json
end_year: 2023
```

### `landing_page_url`

_String:_ A URL for the award's landing page, if available.

```json
landing_page_url: "https://www.nsf.gov/awardsearch/showAward?AWD_ID=1661218"
```

### `doi`

_String:_ The DOI for this award, if available.

```json
doi: "https://doi.org/10.xxxx/award.123"
```

### `provenance`

_String:_ The source of this award data.

```json
provenance: "crossref_work.grants"
```

### `lead_investigator`

_Object:_ Information about the lead investigator (principal investigator) for this award, if available. Contains:

* `given_name`: _String_ — The given name of the investigator
* `family_name`: _String_ — The family name of the investigator
* `orcid`: _String_ — The ORCID identifier of the investigator
* `role_start`: _String_ — When the investigator started this role
* `affiliation`: _Object_ — The investigator's institutional affiliation

```json
lead_investigator: {
    given_name: "Jane",
    family_name: "Smith",
    orcid: "https://orcid.org/0000-0001-2345-6789",
    role_start: "2020-01-01",
    affiliation: {
        name: "University of Example",
        country: "US",
        ids: [
            {
                id: "https://ror.org/example",
                type: "ror",
                asserted_by: "publisher"
            }
        ]
    }
}
```

### `co_lead_investigator`

_Object:_ Information about the co-lead investigator, if available. Has the same structure as [`lead_investigator`](#lead_investigator).

### `investigators`

_List:_ A list of all investigators associated with this award. Each investigator has the same structure as [`lead_investigator`](#lead_investigator).

### `works_api_url`

_String:_ A URL that returns a list of works funded by this award.

```json
works_api_url: "https://api.openalex.org/works?filter=awards.id:G1929887790"
```

### `created_date`

_String:_ The date this Award object was created in the OpenAlex dataset, expressed as an ISO 8601 date string.

```json
created_date: "2025-12-02T00:36:59.534947"
```

### `updated_date`

_String:_ The last time anything in this award object changed, expressed as an ISO 8601 date string.

```json
updated_date: "2025-12-02T00:36:59.534947"
```
