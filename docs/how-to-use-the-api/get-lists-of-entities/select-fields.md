# Select fields

You can use `select` to limit the fields that are returned in results.

* Display works with only the `id`, `doi`, and `display_name` returned in the results\
  [`https://api.openalex.org/works?select=id,doi,display\_name`](https://api.openalex.org/works?select=id,doi,display\_name)

```json
"results": [
  {
    "id": "https://openalex.org/W1775749144",
    "doi": "https://doi.org/10.1016/s0021-9258(19)52451-6",
    "display_name": "PROTEIN MEASUREMENT WITH THE FOLIN PHENOL REAGENT"
  },
  {
    "id": "https://openalex.org/W2100837269",
    "doi": "https://doi.org/10.1038/227680a0",
    "display_name": "Cleavage of Structural Proteins during the Assembly of the Head of Bacteriophage T4"
  },
  // more results removed for brevity
]
```

## Limitations

The fields you choose must exist within the entity (of course). You can only select root-level fields.

So if we have a record like so:

```
"id": "https://openalex.org/W2138270253",
"open_access": {
  "is_oa": true,
  "oa_status": "bronze",
  "oa_url": "http://www.pnas.org/content/74/12/5463.full.pdf"
}
```

You can choose to display `id` and `open_access`, but you will get an error if you try to choose `open_access.is_oa`.

You can use select fields when getting lists of entities or a [single entity](../get-single-entities/select-fields.md). It does not work with [group-by](../get-groups-of-entities.md) or [autocomplete](autocomplete-entities.md).&#x20;
