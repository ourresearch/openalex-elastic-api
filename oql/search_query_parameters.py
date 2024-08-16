import hashlib
from dataclasses import dataclass, field, asdict
from typing import Any, List, Union

from combined_config import all_entities_config


@dataclass
class ExpressionList:
    pass


@dataclass
class ExpressionRule:
    value: Any
    expression_type: str = ""
    operator: str = ""
    prop_id: str = ""


@dataclass
class ExpressionList:
    expression_type: str = ""
    operator: str = ""
    expressions: List[Union['ExpressionList', ExpressionRule]] = field(
        default_factory=list)


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
class SortBy:
    column: str = all_entities_config['works']['sortByDefault']
    direction: str = all_entities_config['works']['sortDirDefault']

    def is_valid(self):
        return self.column in all_entities_config['works'][
            'showOnTablePage'] and self.direction.lower() in {'asc', 'desc'}


@dataclass
class QueryParameters:
    summarize_by: str
    summarize_by_where: SummarizeByWhere = field(
        default_factory=SummarizeByWhere)
    sort_by: SortBy = field(default_factory=SortBy)
    return_columns: List[str] = field(default_factory=list)
    get_works_where: GetWorksWhere = field(default_factory=GetWorksWhere)
    summarize: bool = False

    def id_hash(self) -> str:
        return hashlib.md5(str(asdict(self)).encode()).hexdigest()

    def return_columns_valid(self):
        return all(
            [col in all_entities_config['works']['showOnTablePage'] for col in
             self.return_columns])

    def is_valid(self):
        return all([self.return_columns_valid(),
                    self.sort_by.is_valid(),
                    self.get_works_where.is_valid(),
                    self.summarize_by_where.is_valid()])

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
