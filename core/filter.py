from collections import Counter

from elasticsearch_dsl import Q

from core.utils import get_field


def filter_records(fields_dict, filter_params, s):
    duplicate_keys = find_duplicate_keys(filter_params)
    and_queries = []
    or_queries = []

    for filter in filter_params:
        for key, value in filter.items():
            field = get_field(fields_dict, key)
            field.value = value
            q = field.build_query()
            if key in duplicate_keys:
                or_queries.append(q)  # keys that appear multiple times are "OR" query
            else:
                and_queries.append(q)  # everything else is "AND" query

    combined_and_query = Q("bool", must=and_queries)
    s = s.query(combined_and_query)
    combined_or_query = Q("bool", should=or_queries, minimum_should_match=1)
    s = s.query(combined_or_query)
    return s


def find_duplicate_keys(filter_params):
    """
    Returns a list of keys, where the key is in the params more than once.
    """
    keys = []
    for filter in filter_params:
        for key in filter:
            keys.append(key)
    duplicates = [k for k, v in Counter(keys).items() if v > 1]
    return duplicates
