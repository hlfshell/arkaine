import json
from typing import Any, List, Optional


class Argument:
    def __init__(
        self,
        name: str,
        description: str,
        type: str,
        required: bool = False,
        default: Optional[Any] = None,
    ):
        self.name = name
        self.description = description
        self.type = type
        self.required = required
        self.default = (
            self._convert_value(default, type.lower()) if default else None
        )

    def _convert_value(self, value: Any, type_str: str) -> Any:
        """Convert a value to the appropriate type."""
        if value is None:
            return None

        if isinstance(value, str):
            # Handle basic types
            if type_str == "float":
                return float(value)
            elif type_str == "int":
                return int(value)
            elif type_str == "bool":
                return value.lower() == "true"
            # Handle lists and dicts
            elif type_str.startswith(("list", "dict")):
                try:
                    parsed = json.loads(value)
                    if type_str.startswith("list") and not isinstance(
                        parsed, list
                    ):
                        raise ValueError(f"Expected list, got {type(parsed)}")
                    if type_str.startswith("dict") and not isinstance(
                        parsed, dict
                    ):
                        raise ValueError(f"Expected dict, got {type(parsed)}")
                    return parsed
                except json.JSONDecodeError:
                    return value
        return value

    def __str__(self) -> str:
        out = f"{self.name} - {self.type_str} - Required: "
        out += f"{self.required} - "
        if self.default:
            out += f"Default: {self.default} - "
        out += f"{self.description}"

        return out

    def __repr__(self) -> str:
        return self.__str__()

    @property
    def type_str(self) -> str:
        """
        Since some might pass in the literal type instead of the str of the
        class, we should ensure we convert the type correctly to a string for
        parsing.

        It is not simply str(self.type) as that tends to add "<class 'type'>"
        to the string.
        """
        if isinstance(self.type, str):
            return self.type
        else:
            try:
                return str(self.type).split("'")[1]
            except Exception:
                return str(self.type)

    def to_json(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "type": self.type_str,
            "required": self.required,
            "default": self.default,
        }


class InvalidArgumentException(Exception):
    def __init__(
        self,
        tool_name: str,
        missing_required_args: List[str],
        extraneous_args: List[str],
    ):
        self.__tool_name = tool_name
        self.__missing_required_args = missing_required_args
        self.__extraneous_args = extraneous_args

    def __str__(self):
        out = f"Function {self.__tool_name} was improperly called\n"

        if self.__missing_required_args:
            out += (
                "Missing required arguments: "
                + ", ".join(self.__missing_required_args)
                + "\n"
            )
        if self.__extraneous_args:
            out += (
                "Extraneous arguments: "
                + ", ".join(self.__extraneous_args)
                + "\n"
            )

        return out
