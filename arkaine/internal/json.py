import json
from typing import Any, Dict


def recursive_to_json(value: Any) -> Any:
    """
    recursive_to_json safely converts a singular or collection of objects
    into a JSON serializable friendly format. If the object has a to_json
    method, it will be called with the value. If it *also* has a from_json
    method, the object will have __class__ and __module__ attributes added
    to its serialization so it can be recreated from the JSON.

    Args:
        value: The object to convert to a JSON serializable format.

    Returns:
        The JSON serializable format of the object.
    """
    # Handle primitive types directly
    if isinstance(value, (str, int, float, bool, type(None))):
        return value

    # Create new object/copy for everything else
    if isinstance(value, list):
        return [recursive_to_json(x) for x in value]
    elif isinstance(value, dict):
        return {k: recursive_to_json(v) for k, v in value.items()}
    elif hasattr(value, "to_json"):
        if hasattr(value, "from_json"):
            # Add additional attributes to make the object serializable
            out = value.to_json()
            out["__class__"] = value.__class__.__name__
            out["__module__"] = value.__module__
            return out
        else:
            return value.to_json()
    else:
        try:
            return json.dumps(value)
        except (TypeError, ValueError):
            return str(value)


def recursive_from_json(value: Any, fallback_if_no_class: bool = False) -> Any:
    """
    recursive_from_json safely converts a JSON serializable friendly format
    into a singular or collection of objects. If the object has a from_json
    method, it will be called with the value.

    Args:
        value: The object to convert to a JSON serializable format.
        fallback_if_no_class: Whether to fallback to the JSON if the object
            that has __class__ and __module__ is not found. If False, this
            will raise an error. If True, the dict will be returned as is.

    Returns:
        The object from the JSON serializable format.
    """
    if isinstance(value, dict):
        if "__class__" in value and "__module__" in value:
            try:
                return load_from_attrs(
                    value, value["__module__"], value["__class__"]
                )
            except Exception as e:
                if not fallback_if_no_class:
                    raise e

        # If not, or it failed and we allow it, we do a standard deep dive.
        return {
            k: recursive_from_json(v, fallback_if_no_class)
            for k, v in value.items()
        }
    elif isinstance(value, list):
        return [recursive_from_json(x, fallback_if_no_class) for x in value]
    else:
        return value


def load_from_attrs(value: dict, module: str, classname: str) -> Any:
    """
    Load an object from a dictionary with __class__ and __module__ attributes.
    """
    # Import the module, handling potential submodule chains
    module_parts = module.split(".")
    current_module = __import__(module_parts[0])
    for part in module_parts[1:]:
        current_module = getattr(current_module, part)

    # Get the class from the module
    target_class = getattr(current_module, classname)

    # Call from_json on the class with the value data
    return target_class.from_json(value)
