from core.utils import get_field


def filter_records(fields_dict, filter_params, s):
    for key, value in filter_params.items():
        field = get_field(fields_dict, key)
        field.value = value
        s = field.build_query(s)
    return s
