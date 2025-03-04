from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, List, Union


class QueryOperator(Enum):
    """Supported operators for context queries"""

    EQUALS = "eq"
    NOT_EQUALS = "ne"
    GREATER_THAN = "gt"
    LESS_THAN = "lt"
    GREATER_EQUAL = "ge"
    LESS_EQUAL = "le"
    CONTAINS = "contains"
    NOT_CONTAINS = "not_contains"
    IN = "in"
    NOT_IN = "not_in"


@dataclass
class Check:
    """
    Check represents a single query condition for searching objects.

    Examples:
        - Check("status", QueryOperator.EQUALS, "complete")
        - Check("tool_name", QueryOperator.CONTAINS, "chat")
        - Check("created_at", QueryOperator.GREATER_THAN, 1234567890)
    """

    field: str
    operator: QueryOperator
    value: Any

    def __post_init__(self):
        """Validate the operator is a valid QueryOperator enum value"""
        if not isinstance(self.operator, QueryOperator):
            raise ValueError(
                f"Invalid operator '{self.operator}'. Must be a "
                "QueryOperator enum value."
            )

    def __call__(self, obj: Any) -> bool:
        """
        Check if an object matches this query condition.

        Args:
            obj: The object to check against (can be a Context, dict, or any
                object)

        Returns:
            bool: True if the object matches the query condition
        """
        # Handle nested field paths (e.g., "tool.name" or "args.test")
        field_parts = self.field.split(".")
        current = obj

        # Navigate through the field path
        for i, part in enumerate(field_parts):
            # Handle dictionary-like objects
            if isinstance(current, dict):
                if part not in current:
                    return False
                current = current[part]
            # Handle special case for "args" attribute that might be a dict
            elif i == 0 and part == "args" and hasattr(current, "args"):
                if len(field_parts) < 2:  # If just "args" with no subfield
                    current = current.args
                else:  # If "args.something"
                    if not current.args or not isinstance(current.args, dict):
                        return False
                    if field_parts[1] not in current.args:
                        return False
                    current = current.args[field_parts[1]]
                    break  # nested field complete- break
            # Handle regular object attributes
            elif hasattr(current, part):
                current = getattr(current, part)
            else:
                return False

        field_value = current

        if self.operator == QueryOperator.EQUALS:
            return field_value == self.value
        elif self.operator == QueryOperator.NOT_EQUALS:
            return field_value != self.value
        elif self.operator == QueryOperator.GREATER_THAN:
            return field_value > self.value
        elif self.operator == QueryOperator.LESS_THAN:
            return field_value < self.value
        elif self.operator == QueryOperator.GREATER_EQUAL:
            return field_value >= self.value
        elif self.operator == QueryOperator.LESS_EQUAL:
            return field_value <= self.value
        elif self.operator == QueryOperator.CONTAINS:
            return self.value in field_value
        elif self.operator == QueryOperator.NOT_CONTAINS:
            return self.value not in field_value
        elif self.operator == QueryOperator.IN:
            return field_value in self.value
        elif self.operator == QueryOperator.NOT_IN:
            return field_value not in self.value

        return False

    def __add__(self, other: Union[Check, Query]) -> Query:
        if isinstance(other, Query):
            return Query(self._checks + other._checks)
        elif isinstance(other, Check):
            return Query(self._checks + [other])
        else:
            raise ValueError(
                "Unsupported operand type(s) for +: "
                f"'Query' and '{type(other)}'"
            )


class Query:

    def __init__(self, checks: List[Check]):
        self._checks = checks

    def __call__(self, obj: Any) -> bool:
        return all(check(obj) for check in self._checks)

    def __add__(self, other: Union[Query, Check]) -> Query:
        if isinstance(other, Query):
            return Query(self._checks + other._checks)
        elif isinstance(other, Check):
            return Query(self._checks + [other])
        else:
            raise ValueError(
                "Unsupported operand type(s) for +: "
                f"'Query' and '{type(other)}'"
            )
