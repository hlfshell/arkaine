import json
from typing import Any


def recursive_to_json(value: Any) -> Any:
    # Handle primitive types directly
    if isinstance(value, (str, int, float, bool, type(None))):
        return value

    # Create new object/copy for everything else
    if isinstance(value, list):
        return [recursive_to_json(x) for x in value]
    elif isinstance(value, dict):
        return {k: recursive_to_json(v) for k, v in value.items()}
    elif hasattr(value, "to_json"):
        return recursive_to_json(value.to_json())
    else:
        try:
            return json.dumps(value)
        except (TypeError, ValueError):
            return str(value)
