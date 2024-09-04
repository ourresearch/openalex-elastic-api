import hashlib
import json
import random
import string
from dataclasses import fields, is_dataclass, MISSING, asdict
from typing import Type, Any


def from_dict(cls: Type[Any], data: dict) -> Any:
    if not is_dataclass(cls):
        return data

    kwargs = {}
    for f in fields(cls):
        if f.init:  # Only include fields that are expected in the __init__ method
            field_value = data.get(f.name, MISSING)
            if field_value is MISSING:
                continue

            if is_dataclass(f.type):
                kwargs[f.name] = from_dict(f.type, field_value)
            elif isinstance(field_value, dict):
                kwargs[f.name] = from_dict(f.type, field_value)
            elif isinstance(field_value, list) and f.type.__args__:
                # Handle lists of dataclass instances
                item_type = f.type.__args__[0]
                kwargs[f.name] = [
                    from_dict(item_type, item) if isinstance(item,
                                                             dict) else item
                    for item in field_value
                ]
            else:
                kwargs[f.name] = field_value

    return cls(**kwargs)


def parse_bool(value: str) -> bool:
    value = value.strip().lower()
    if value in ['true', '1', 'yes', 'y', 'on']:
        return True
    elif value in ['false', '0', 'no', 'n', 'off']:
        return False
    else:
        raise ValueError(f"Cannot parse boolean from {value}")


def dataclass_id_hash(obj: Any) -> str:
    return hashlib.md5(str(asdict(obj)).encode()).hexdigest()


def random_md5(length: int = 12) -> str:
    random_string = ''.join(
        random.choices(string.ascii_letters + string.digits, k=length))
    return hashlib.md5(random_string.encode()).hexdigest()


def queries_equal(generated_oqo, expected_oqo, ignore_properties=None, path=''):
    if ignore_properties is None:
        ignore_properties = []

    def create_difference(prop, value1, value2):
        return {
            'equal': False,
            'difference_path': f"{path}{prop}",
            'path_expected': value2,
            'path_actual': value1
        }

    def normalize_operator(operator):
        operator_map = {
            '<': 'is less than',
            '<=': 'is less than or equal to',
            '>': 'is greater than',
            '>=': 'is greater than or equal to',
            '=': 'is',
            '!=': 'is not'
        }
        return operator_map.get(operator, operator)

    def compare_filters(filters1, filters2, filter_path):
        if filters1 is None and filters2 is None:
            return {'equal': True}
        if filters1 is None or filters2 is None:
            return create_difference(filter_path, filters1, filters2)

        queue1 = filters1.copy()
        queue2 = filters2.copy()

        while queue1 and queue2:
            filter1 = queue1.pop(0)
            match_found = False

            for i, filter2 in enumerate(queue2):
                if filters_match(filter1, filter2):
                    del queue2[i]
                    match_found = True
                    break

            if not match_found:
                return create_difference(f"{filter_path}unmatched filter",
                                         filter1, None)

        if queue1 or queue2:
            return create_difference(f"{filter_path}remaining filters", queue1,
                                     queue2)

        return {'equal': True}

    def filters_match(filter1, filter2):
        if (filter1.get('type') != filter2.get('type') or
                filter1.get('subjectEntity') != filter2.get('subjectEntity') or
                normalize_operator(
                    filter1.get('operator')) != normalize_operator(
                    filter2.get('operator'))):
            return False

        if filter1.get('type') == 'leaf':
            return (filter1.get('column_id') == filter2.get('column_id') and
                    are_values_equal(filter1.get('value'),
                                     filter2.get('value')))
        elif filter1.get('type') == 'branch':
            return len(filter1.get('children', [])) == len(
                filter2.get('children', []))

        return False

    def are_values_equal(value1, value2):
        if value1 == value2:
            return True

        def is_null_or_empty(val):
            return val is None or (isinstance(val, list) and len(val) == 0)

        if is_null_or_empty(value1) or is_null_or_empty(value2):
            return is_null_or_empty(value1) and is_null_or_empty(value2)

        if isinstance(value1, (int, float)) and isinstance(value2, str):
            return float(value1) == float(value2)
        if isinstance(value1, str) and isinstance(value2, (int, float)):
            return float(value1) == float(value2)

        return json.dumps(value1, sort_keys=True) == json.dumps(value2,
                                                                sort_keys=True)

    # Handle empty objects
    if not generated_oqo and not expected_oqo:
        return {'equal': True}

    # Compare get_rows (required property)
    if 'get_rows' not in generated_oqo or 'get_rows' not in expected_oqo:
        return create_difference('get_rows', generated_oqo.get('get_rows'),
                                 expected_oqo.get('get_rows'))

    if generated_oqo['get_rows'] != expected_oqo['get_rows']:
        return create_difference('get_rows', generated_oqo['get_rows'],
                                 expected_oqo['get_rows'])

    # Compare other properties
    properties = ['sort_by_column', 'sort_by_order', 'show_columns']
    for prop in properties:
        if prop not in ignore_properties:
            if not are_values_equal(generated_oqo.get(prop),
                                    expected_oqo.get(prop)):
                return create_difference(prop, generated_oqo.get(prop),
                                         expected_oqo.get(prop))

    # Compare filter_works
    filter_works_result = compare_filters(generated_oqo.get('filter_works'),
                                          expected_oqo.get('filter_works'),
                                          'filter_works.')
    if not filter_works_result['equal']:
        return filter_works_result

    # Compare filter_aggs
    filter_aggs_result = compare_filters(generated_oqo.get('filter_aggs'),
                                         expected_oqo.get('filter_aggs'),
                                         'filter_aggs.')
    if not filter_aggs_result['equal']:
        return filter_aggs_result

    return {'equal': True}