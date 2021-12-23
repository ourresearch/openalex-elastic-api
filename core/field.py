from dataclasses import dataclass
from typing import Optional


@dataclass
class Field:
    """
    Defines a field that can be filtered, grouped, and sorted.
    """

    param: str
    value: Optional[str, int]
    custom_es_field: Optional[str] = None
    is_bool_query: bool = False
    is_date_query: bool = False
    is_range_query: bool = False

    def es_field(self) -> str:
        if self.custom_es_field:
            field = self.custom_es_field
        elif "." in self.param:
            field = self.param.replace(".", "__")
        else:
            field = self.param
        return field
