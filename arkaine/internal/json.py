import json
from typing import Any, Dict


def recursive_to_json(value: Any, serial_wrap: bool = False) -> Any:
    """
    recursive_to_json safely converts a singular or collection of objects
    into a JSON serializable friendly format.

    Args:
        value: The object to convert to a JSON serializable format.
        serial_wrap: Whether to wrap the value in a SerialWrapper if it
            has a to_json and from_json method

    Returns:
        The JSON serializable format of the object.
    """
    # Handle primitive types directly
    if isinstance(value, (str, int, float, bool, type(None))):
        return value

    # Create new object/copy for everything else
    if isinstance(value, list):
        return [recursive_to_json(x, serial_wrap) for x in value]
    elif isinstance(value, dict):
        return {k: recursive_to_json(v, serial_wrap) for k, v in value.items()}
    elif hasattr(value, "to_json"):
        if hasattr(value, "from_json") and serial_wrap:
            # Create a SerialWrapper and convert to JSON
            return SerialWrapper(value).to_json()
        else:
            return value.to_json()
    else:
        try:
            return json.dumps(value)
        except (TypeError, ValueError):
            return str(value)


def recursive_from_json(value: Any) -> Any:
    """
    recursive_from_json safely converts a JSON serializable friendly format
    into a singular or collection of objects. If the object has a from_json
    method, it will be called with the value.

    Args:
        value: The object to convert to a JSON serializable format.

    Returns:
        The object from the JSON serializable format.
    """
    if isinstance(value, dict):
        # Check if this is a SerialWrapper format
        if SerialWrapper.is_serial_wrapper(value):
            return SerialWrapper.from_json(value)
        return {k: recursive_from_json(v) for k, v in value.items()}
    elif isinstance(value, list):
        return [recursive_from_json(x) for x in value]
    else:
        return value


class SerialWrapper:
    """
    SerialWrapper is a helper class that wraps an object and provides a JSON
    serializable format *with* the ability to reconstruct the object, handling
    submodule chains and class instantiation. It should be utilized when dealing
    with serialization that will require reconstruction of the object in the
    future.
    """

    def __init__(self, value: Any):
        self.__value = value
        self.__class = type(value)
        self.__module = value.__module__

    @property
    def value(self) -> Any:
        return self.__value

    @classmethod
    def is_serial_wrapper(cls, value: Dict[str, Any]) -> bool:
        return "type" in value and "module" in value and "value" in value

    def to_json(self) -> dict:
        return {
            "type": self.__class.__name__,
            "module": self.__module,
            "value": recursive_to_json(self.__value),
        }

    @classmethod
    def from_json(cls, data: dict) -> Any:
        module_path = data["module"]
        class_name = data["type"]
        value_data = data["value"]

        # Import the module, handling potential submodule chains
        module_parts = module_path.split(".")
        current_module = __import__(module_parts[0])

        for part in module_parts[1:]:
            current_module = getattr(current_module, part)

        # Get the class from the module
        target_class = getattr(current_module, class_name)

        # Call from_json on the class with the value data
        return target_class.from_json(value_data)
