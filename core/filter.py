from elasticsearch_dsl import Q, Search

from core.exceptions import APIQueryParamsError
from core.utils import get_field


def filter_records(fields_dict, filter_params, s):
    for filter in filter_params:
        for key, value in filter.items():
            field = get_field(fields_dict, key)

            # OR queries have | in the param values
            if "|" in value:
                s = handle_or_query(field, s, value)

            # everything else is an AND query
            else:
                field.value = value
                q = field.build_query()
                s = s.query(q)
    return s


def handle_or_query(field, s, value):
    or_queries = []

    if value.startswith("!"):
        # negate everything in values after !, like: NOT (42 or 43)
        for or_value in value.split("|"):
            or_value = or_value.replace("!", "")
            field.value = or_value
            q = field.build_query()
            not_query = ~Q("bool", must=q)
            s = s.query(not_query)
    else:
        # standard OR query, like: 42 or 43
        for or_value in value.split("|"):
            if or_value.startswith("!"):
                raise APIQueryParamsError(
                    f"The ! operator can only be used at the beginning of an OR query, "
                    f"like /works?filter=concepts.id:!C144133560|C15744967, meaning NOT (C144133560 or C15744967). Problem "
                    f"value: {or_value}"
                )
            field.value = or_value
            q = field.build_query()
            or_queries.append(q)
        combined_or_query = Q("bool", should=or_queries, minimum_should_match=1)
        s = s.query(combined_or_query)
    return s


def filter_records_filters_view(fields_dict, filter_params, ms):
    meta_results = []
    for filter in filter_params:
        for key, value in filter.items():
            field = get_field(fields_dict, key)

            field_meta = {"key": key, "type": type(field).__name__, "values": []}

            # OR queries have | in the param values
            if "|" in value:
                if value.startswith("!"):
                    field_meta["is_negated"] = True
                    # negate everything in values after !, like: NOT (42 or 43)
                    for or_value in value.split("|"):
                        or_value = or_value.replace("!", "")
                        field.value = or_value
                        field_meta["values"].append(
                            {"value": or_value, "display_name": or_value}
                        )
                        q = field.build_query()
                        s = Search()
                        s = s.extra(track_total_hits=True, size=0)
                        ms = ms.add(s.query(q))
                else:
                    field_meta["is_negated"] = False
                    # standard OR query, like: 42 or 43
                    for or_value in value.split("|"):
                        if or_value.startswith("!"):
                            raise APIQueryParamsError(
                                f"The ! operator can only be used at the beginning of an OR query, "
                                f"like /works?filter=concepts.id:!C144133560|C15744967, meaning NOT (C144133560 or C15744967). Problem "
                                f"value: {or_value}"
                            )
                        field.value = or_value
                        field_meta["values"].append(
                            {"value": or_value, "display_name": or_value}
                        )
                        q = field.build_query()
                        s = Search()
                        s = s.extra(track_total_hits=True, size=0)
                        ms = ms.add(s.query(q))
            else:
                if value.startswith("!"):
                    field.value = value[1:]  # pass value without negation
                    field_meta["is_negated"] = True
                    field_meta["values"].append(
                        {"value": value[1:], "display_name": value[1:]}
                    )
                else:
                    field.value = value
                    field_meta["is_negated"] = False
                    field_meta["values"].append({"value": value, "display_name": value})
                q = field.build_query()
                s = Search()
                s = s.extra(track_total_hits=True, size=0)
                ms = ms.add(s.query(q))
            meta_results.append(field_meta)
    return ms, meta_results
