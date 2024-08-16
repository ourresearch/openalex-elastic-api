from dataclasses import fields, is_dataclass, MISSING
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
