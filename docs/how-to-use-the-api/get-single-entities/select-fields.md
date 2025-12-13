# Select fields

You can use `select` to choose top-level fields you want to see in a result.

* Display `id` and `display_name` for a work\
  [`https://api.openalex.org/works/W2138270253?select=id,display_name`](https://api.openalex.org/works/W2138270253?select=id,display_name)

```json
{
  id: "https://openalex.org/W2138270253",
  display_name: "DNA sequencing with chain-terminating inhibitors"
}
```

Read more about this feature [here](../get-lists-of-entities/select-fields.md).
