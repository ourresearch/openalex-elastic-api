import hashlib
from dataclasses import dataclass, field, asdict
from typing import Any, List, Union, Dict

from combined_config import all_entities_config
from oql.util import dataclass_id_hash


@dataclass
class ExpressionList:
    pass


@dataclass
class ExpressionRule:
    value: Any
    expression_type: str = "rule"
    operator: str = ""
    prop_id: str = ""

    def is_valid(self):
        operator_valid = self.expression_type in {'is', 'is not', 'is in',
                                                  'is not in', 'includes',
                                                  'does not include'}
        return operator_valid


@dataclass
class ExpressionList:
    expression_type: str = "list"
    operator: str = "AND"
    expressions: List[Union['ExpressionList', ExpressionRule]] = field(
        default_factory=list)

    def is_valid(self):
        operator_valid = self.operator in {'AND', 'OR'}
        return operator_valid


@dataclass
class GetWorksWhere:
    as_string: str = ""
    expressions: ExpressionList = field(default_factory=ExpressionList)

    def is_valid(self):
        # TODO implement
        # raise NotImplemented
        return True


@dataclass
class SummarizeByWhere:
    as_string: str = ""
    expressions: ExpressionList = field(default_factory=ExpressionList)

    def is_valid(self):
        # TODO implement
        # raise NotImplemented
        return True


@dataclass
class Clause:
    pass


@dataclass
class Clause:
    id: str
    column_name: str
    value: Any
    parent: 'Clause'

    def __post_init__(self):
        self.id = self.id if self.id else dataclass_id_hash(self)

    def is_valid(self):
        return self.column_name in all_entities_config['works']['showOnTablePage']

    def update_clause(self, _id: str, new_clause: Clause):
        current = self
        while current is not None:
            if current.id == _id:
                current.parent = new_clause.parent
                current.column_name = new_clause.column_name
                current.value = new_clause.value
                return True
            current = current.parent
        return False


@dataclass
class SortBy:
    column: str = all_entities_config['works']['sortByDefault']
    direction: str = all_entities_config['works']['sortDirDefault']

    def is_valid(self, return_cols):
        return self.column in return_cols and self.direction.lower() in {'asc', 'desc'}


@dataclass
class QueryParameters:
    summarize_by: str
    summarize_by_where: Dict = field(default_factory=dict)
    sort_by: SortBy = field(default_factory=SortBy)
    return_columns: List[str] = field(default_factory=list)
    get_works_where: Dict = field(default_factory=dict)
    summarize: bool = False

    def id_hash(self) -> str:
        return dataclass_id_hash(self)

    def return_columns_valid(self):
        return all(
            [col in all_entities_config['works']['showOnTablePage'] for col in
             self.return_columns])

    def is_valid(self):
        return all([self.return_columns_valid(),
                    self.sort_by.is_valid(self.return_columns)])

    def add_return_column(self, column: str):
        if column not in all_entities_config['works']['showOnTablePage']:
            return False
        self.return_columns.append(column)
        self.return_columns = list(set(self.return_columns))
        return True

    def remove_return_column(self, column: str):
        if column not in self.return_columns:
            return False
        self.return_columns.remove(column)
        return True
