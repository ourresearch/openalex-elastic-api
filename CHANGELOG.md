# Changelog

* Add key_display_name to group by queries. [2022-02-15]
* Refactor OR queries to use | separator, like `/works?filter=author.id:A2565156079|A2564890435`. [2022-02-10]
* Duplicate filter keys now work as AND queries. [2022-02-10]
* Support OR query with alias. Resolve bug that occurred when different pairs of keys are used with an OR query. [2022-02-07]
* Implement OR query by entering param name twice, such as `filter=publication_year:1981,publication_year:1982`. [2022-02-04]
* Increase per-page limit to 200. [2022-02-04]
* Improve search algorithm so that cited_by_count has a bigger impact on results. [2022-01-28]
* Resolve relevance_score sort bug. [2022-01-27]
* Improve works performance by storing documents in order of publication_date. [2022-01-27]
* Add `raw_affiliation_string` to authorships object. Change `cited_by_url` to a string rather than a list. [2022-01-27]
* Fix range queries such as `publication_year:1981-1982` so it is `greater than or equal` to `less than or equal`. [2022-01-25]
* Update works endpoint to display new abstract inverted index data. [2022-01-22]
* Allow search queries to contain colons within the search string. [2022-01-16]
* Add support for phrase search with quotes: `works?filter=title.search:"type 1 diabetes control"` which ensures words 
follow each other in the exact order of the query.
* Remove support for bracketed or queries, like `concepts.id:[C15708023, C41008148]`. [2022-01-16] 
* Add `from_publication_date` and `to_publication_date` filter to works endpoint. Of note, `from_publication_date:2020-05-07` 
is greater than or equal to that date, while the filter `publication_date:>2020-05-07` is only greater than that date. The 
same differences applies for `to_publication_date` and `publication_date:<` filter. These new fields can be hyphenated. [2022-01-13]
* Add support for multiple terms OR filters, like `concepts.id:[C15708023, C41008148]`. [2022-01-12]
* Add support for numeric range filters, such as `cited_by_count:100-150`. [2022-01-12]
* Fix: Ensure sort params work properly when searching. [2022-01-11] 
* Boosted search results for every entity using cited by count. Documents with higher cited by count are more
likely to be shown first. [2022-01-11]
* Any query parameter or field can be written as hyphenated or underscore. 
So `group_by=publication_year` and `group-by=publication-year` will work the same. [2022-01-10]