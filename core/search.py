from elasticsearch_dsl import Q


def search_records(search, s):
    if search:
        basic_query = Q(
            "match",
            display_name={
                "query": search,
                "operator": "and",
            },
        ) | Q(
            "match_phrase",
            display_name={"query": search, "boost": 2},
        )
        function_query = Q(
            "function_score",
            functions={
                "field_value_factor": {
                    "field": "cited_by_count",
                    "factor": 1,
                    "modifier": "sqrt",
                    "missing": 1,
                }
            },
            query=basic_query,
            boost_mode="sum",
        )
        s = s.query(function_query)
    return s
