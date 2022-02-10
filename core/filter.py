from elasticsearch_dsl import Q

from core.utils import get_field


def filter_records(fields_dict, filter_params, s):
    for filter in filter_params:
        for key, value in filter.items():
            field = get_field(fields_dict, key)

            # OR queries have | in the param values
            or_queries = []
            if "|" in value:
                for or_value in value.split("|"):
                    field.value = or_value
                    q = field.build_query()
                    or_queries.append(q)
                combined_or_query = Q("bool", should=or_queries, minimum_should_match=1)
                s = s.query(combined_or_query)

            # everything else is an AND query
            else:
                field.value = value
                q = field.build_query()
                s = s.query(q)
    return s
