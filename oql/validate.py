from typing import List, Dict, Optional

import requests


"""
From: https://github.com/ourresearch/oqo-validate/blob/main/oqo_validate/validate.py
"""


class OQOValidator:
    BRANCH_OPERATORS = {'and', 'or'}
    LEAF_OPERATORS = {'is', 'is not', 'contains', 'does not contain',
                      'is greater than', 'is less than', '>', '<', 'is in',
                      'is not in'}
    FILTER_TYPES = {'branch', 'leaf'}

    def __init__(self, config: Optional[Dict] = None):
        self.ENTITIES_CONFIG = config or self._fetch_entities_config()

    @staticmethod
    def _fetch_entities_config():
        r = requests.get('https://api.openalex.org/entities/config')
        r.raise_for_status()
        return r.json()

    @staticmethod
    def _safe_lower(o):
        return o.lower() if isinstance(o, str) else o

    @staticmethod
    def _flatten_keys_and_values(dicts: List[dict]) -> List:
        dicts = [item for d in dicts for item in d.items()]
        return [OQOValidator._safe_lower(element) for pair in dicts for element
                in pair]

    @staticmethod
    def _formatted_country_value(country_code):
        country_code = country_code.lower()
        return f'countries/{country_code}' if 'countries' not in country_code else country_code

    def _entity_possible_values(self, entity):
        return set(self._flatten_keys_and_values(
            self.ENTITIES_CONFIG[entity].get('values', []) or []))

    def _get_entity_column(self, entity, column_id_or_name, actions=None):
        if not actions:
            actions = []
        for _, col in self.ENTITIES_CONFIG[entity].get('columns', {}).items():
            valid_names = {col['id'], col['displayName'],
                           col.get('redshiftDisplayColumn')}
            if column_id_or_name in valid_names and all(
                    [action in col.get('actions', []) for action in actions]):
                return col
        return None

    def _validate_leaf(self, leaf_filter, get_rows_entity, origin):
        if get_rows_entity == 'works' and origin != 'filter_works':
            return f'works filter cannot be in {origin}'
        if subj_entity := leaf_filter.get('subjectEntity'):
            if subj_entity == 'works' and origin != 'filter_works':
                return False, f'work filter cannot be in {origin}'
            elif subj_entity != 'works' and origin != 'filter_aggs':
                return False, f'agg filter cannot be in {origin}'
        col = self._get_entity_column(get_rows_entity, leaf_filter['column_id'])
        if not col:
            return False, f'{get_rows_entity}.{leaf_filter["column_id"]} not a valid filter column'
        if leaf_filter.get('operator', 'is') not in self.LEAF_OPERATORS:
            return False, f'{leaf_filter["operator"]} not a valid leaf operator'
        obj_entity = col.get('objectEntity')
        if obj_entity:
            possible_values = self._entity_possible_values(obj_entity)
            value = leaf_filter[
                'value'] if obj_entity != 'countries' else self._formatted_country_value(
                leaf_filter['value'])
            if possible_values and self._safe_lower(
                    value) not in possible_values:
                return False, f'{leaf_filter["value"]} not a valid value for {obj_entity}'
        return True, None

    def _validate_branch(self, branch_filter):
        if not branch_filter.get('children'):
            return False, f'Branch {branch_filter.get("id")} has empty children'
        if branch_filter['operator'] not in self.BRANCH_OPERATORS:
            return False, f'{branch_filter["operator"]} not a valid branch operator'
        return True, None

    def _validate_filter(self, filter_node, get_rows_entity, origin):
        # if filter_node['type'] not in self.FILTER_TYPES:
        #     return False, f'{filter_node.get("type")} not a valid filter type'
        # if filter_node['type'] == 'branch':
        #     return self._validate_branch(filter_node)
        # elif filter_node['type'] == 'leaf':
        return self._validate_leaf(filter_node, get_rows_entity, origin)
        # return False, f'{filter_node.get("type")} not a valid filter type'

    def _validate_sort_by_column(self, sort_by_column, entity='works'):
        col = self._get_entity_column(entity, sort_by_column)
        if not col:
            return False, f'{entity}.{sort_by_column} not a valid sort column'
        return True, None

    @staticmethod
    def _validate_sort_order(sort_order):
        if sort_order not in {'asc', 'desc'}:
            return False, f'{sort_order} not a valid sort order'
        return True, None

    def _validate_show_columns(self, show_columns, entity='works'):
        for column in show_columns:
            col = self._get_entity_column(entity, column)
            if not col:
                return False, f'{entity}.{column} not a valid return column'
        return True, None

    def _validate_get_rows(self, get_rows):
        if get_rows not in self.ENTITIES_CONFIG.keys() and get_rows != 'summary':
            return False, f'{get_rows} is not a valid entity'
        return True, None

    def _validate(self, oqo):
        ok, err = self._validate_get_rows(oqo.get('get_rows'))
        if not ok:
            return False, err
        for _filter in oqo.get('filter_works', []):
            ok, error = self._validate_filter(_filter, 'works', 'filter_works')
            if not ok:
                return False, error

        for _filter in oqo.get('filter_aggs', []):
            ok, error = self._validate_filter(_filter, oqo.get('get_rows'), 'filter_aggs')
            if not ok:
                return False, error

        if return_cols := oqo.get('show_columns', []):
            if oqo.get('get_rows') == 'summary':
                # TODO: not sure yet
                pass
            else:
                ok, error = self._validate_show_columns(return_cols, entity=oqo.get('get_rows'))
                if not ok:
                    return False, error
        if sort_by_col := oqo.get('sort_by_column'):
            if oqo.get('get_rows') == 'summary':
                # TODO: not sure yet
                pass
            else:
                ok, error = self._validate_sort_by_column(sort_by_col, oqo.get('get_rows') or 'works')
                if not ok:
                    return False, error
        if sort_by_dir := oqo.get('sort_by_order'):
            ok, error = self._validate_sort_order(sort_by_dir)
            if not ok:
                return False, error
        return True, None

    def validate(self, oqo, return_exc=False):
        if return_exc:
            try:
                return self._validate(oqo)
            except Exception as e:
                return False, str(e)
        return self._validate(oqo)