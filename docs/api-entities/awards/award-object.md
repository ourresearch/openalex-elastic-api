# Award object

These are the fields in an award object. When you use the API to get a single award or lists of awards, this is what's returned.

### `id`

_String:_ The OpenAlex ID for this award.

```json
id: "https://openalex.org/G5453342221"
```

### `display_name`

_String:_ The name or title of the award, if available.

```json
display_name: "Implementation of activities described in the Roadmap to Fusion during Horizon 2020 through a Joint programme of the members of the EUROfusion consortium"
```

### `description`

_String:_ A description of the award, if available.

```json
description: "A Roadmap to the realization of fusion energy was adopted by the EFDA system at the end of 2012. The roadmap aims at achieving all the necessary know-how to start the construction of a demonstration power plant (DEMO) by 2030..."
```

### `funder_award_id`

_String:_ The award identifier as assigned by the funder (e.g., the grant number).

```json
funder_award_id: "633053"
```

### `funder`

_Object:_ Information about the funder that issued this award. Contains:

* `id`: _String_ — The OpenAlex ID for the funder
* `display_name`: _String_ — The name of the funder
* `ror`: _String_ — The ROR ID for the funder
* `doi`: _String_ — The DOI for the funder

```json
funder: {
    id: "https://openalex.org/F4320337670",
    display_name: "H2020 Euratom",
    doi: "https://doi.org/10.13039/100010687"
}
```

### `funded_outputs`

_List:_ A list of OpenAlex Work IDs that were funded by this award.

```json
funded_outputs: [
    "https://openalex.org/W2959949293",
    "https://openalex.org/W3181133739",
    "https://openalex.org/W2755925992",
    // ... and more
]
```

### `funded_outputs_count`

_Integer:_ The number of works funded by this award.

```json
funded_outputs_count: 1350
```

### `amount`

_Float:_ The monetary amount of the award, if available.

```json
amount: 678800000.0
```

### `currency`

_String:_ The currency of the award amount (e.g., "USD", "EUR"), if available.

```json
currency: "EUR"
```

### `funding_type`

_String:_ The type of funding provided (e.g., "grant", "fellowship"), if available.

```json
funding_type: "grant"
```

### `funder_scheme`

_String:_ The specific funding scheme or program under which the award was made, if available.

```json
funder_scheme: "EURATOM"
```

### `start_date`

_String:_ The start date of the award, formatted as an ISO 8601 date string, if available.

```json
start_date: "2014-01-01"
```

### `end_date`

_String:_ The end date of the award, formatted as an ISO 8601 date string, if available.

```json
end_date: "2022-12-31"
```

### `start_year`

_Integer:_ The year when the award started, if available.

```json
start_year: 2014
```

### `end_year`

_Integer:_ The year when the award ends or ended, if available.

```json
end_year: 2022
```

### `landing_page_url`

_String:_ A URL for the award's landing page, if available.

```json
landing_page_url: "https://cordis.europa.eu/project/id/633053"
```

### `doi`

_String:_ The DOI for this award, if available.

```json
doi: "https://doi.org/10.3030/633053"
```

### `provenance`

_String:_ The source of this award data.

```json
provenance: "crossref_work"
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
works_api_url: "https://api.openalex.org/works?filter=awards.id:G5453342221"
```

### `created_date`

_String:_ The date this Award object was created in the OpenAlex dataset, expressed as an ISO 8601 date string.

```json
created_date: "2022-12-12T12:41:08"
```

### `updated_date`

_String:_ The last time anything in this award object changed, expressed as an ISO 8601 date string.

```json
updated_date: "2022-12-14T06:02:06"
```
