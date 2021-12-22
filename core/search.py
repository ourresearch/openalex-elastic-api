from elasticsearch_dsl import Q


def search_records(search, s):
    if search:
        q = (
            # Q("match", work_title={"query": search_params["title"]})
            Q(
                "match",
                display_name={
                    "query": search,
                    "operator": "and",
                },
            )
            | Q(
                "match_phrase",
                display_name={"query": search, "boost": 2},
            )
        )
        s = s.query(q)
        # alternate method
        # s = s.query(
        #     "match_phrase", work_title={"query": search_params["title"], "slop": 1}
        # )
    return s
