import json
from typing import Any


def recursive_to_json(value: Any) -> Any:
    if hasattr(value, "to_json"):
        value = value.to_json()
    if isinstance(value, (str, int, float, bool, type(None))):
        return value
    elif isinstance(value, list):
        value = [recursive_to_json(x) for x in value]
    elif isinstance(value, dict):
        for k, v in value.items():
            value[k] = recursive_to_json(v)
    else:
        try:
            value = json.dumps(value)
        except (TypeError, ValueError):
            value = str(value)
    return value
