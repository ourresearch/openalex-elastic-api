from elasticsearch_dsl import Q


def search_records_full(search):
    if search:
        basic_query = Q("match", display_name={"query": search, "operator": "and"}) | Q(
            "match_phrase", display_name={"query": search, "boost": 2}
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
            boost_mode="multiply",
        )
    else:
        function_query = Q("match_all")
    return function_query


def search_records_phrase(search):
    basic_query = Q(
        "match_phrase",
        display_name={"query": search},
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
        boost_mode="multiply",
    )
    return function_query
