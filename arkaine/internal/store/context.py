from __future__ import annotations

import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Union

from arkaine.tools.tool import Context


@dataclass
class ContextAttributes:
    """
    ContextAttributes are the attributes that can be used to query a context.
    """

    id: Optional[str] = None
    tool: Optional[str] = None
    status: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    parent: Optional[str] = None
    root: Optional[str] = None
    is_root: Optional[bool] = None


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
    Check represents a single query condition for searching contexts.

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
                f"Invalid operator '{self.operator}'. Must be a QueryOperator enum value."
            )

    def __call__(self, context: Context) -> bool:
        """
        Check if a context matches this query condition.

        Args:
            context: The context to check against

        Returns:
            bool: True if the context matches the query condition
        """
        # Handle nested field paths (e.g., "tool.name" or "args.test")
        field_parts = self.field.split(".")
        current = context

        # Special handling for args since it's a dict
        if field_parts[0] == "args":
            if not context.args or len(field_parts) < 2:
                return False
            field_value = context.args.get(field_parts[1])
        else:
            # Handle other nested attributes
            for part in field_parts:
                if not hasattr(current, part):
                    return False
                current = getattr(current, part)
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

    def __call__(self, context: Context) -> bool:
        return all(check(context) for check in self._checks)

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


class ContextStore(ABC):
    """
    The goal of a context store is to provide a way to store, query for, and
    retrieve contexts over several executions.
    """

    def __init__(self):
        super().__init__()

    @abstractmethod
    def get_context(self, id: str) -> Optional[Context]:
        """
        get_context retrieves a context from the store by its id.

        Args:
            id: The unique identifier of the context

        Returns:
            Context: The context if found, None otherwise
        """
        pass

    @abstractmethod
    def query_contexts(
        self, query: Union[Query, List[Query], Check, List[Check]]
    ) -> List[Context]:
        """
        query_contexts queries the store for contexts that match all the given
        queries.

        Args:
            query: A query, list of queries, check, or list of checks that is
                used to filter the contexts to a desired subset.

        Returns:
            List[Context]: List of contexts that match all query conditions
        """
        pass

    @abstractmethod
    def save(self, context: Context) -> None:
        """
        save_context saves a context to the store.

        Args:
            context: The context to save
        """
        pass

    @abstractmethod
    def load(self) -> "ContextStore":
        """
        load loads a context store from the store.

        Returns:
            ContextStore: The loaded context store
        """
        pass


class InMemoryContextStore(ContextStore):
    """
    MemoryContextStore is a simple in-memory context store.
    """

    def __init__(self, contexts: Dict[str, Context] = {}):
        super().__init__()
        self._contexts: Dict[str, Context] = contexts

    def get_context(self, id: str) -> Optional[Context]:
        return self._contexts.get(id)

    def query_contexts(
        self, query: Union[Query, List[Query], Check, List[Check]]
    ) -> List[Context]:
        if isinstance(query, List):
            q = Query()
            for i in query:
                q += i
            query = q
        elif isinstance(query, Check):
            query = Query([query])

        return [
            context for context in self._contexts.values() if query(context)
        ]

    def save(self, context: Context) -> None:
        self._contexts[context.id] = context

    @staticmethod
    def load(self) -> "ContextStore":
        raise NotImplementedError("InMemoryContextStore is not persistent")

    def __enter__(self) -> InMemoryContextStore:
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        pass


class FileContextStore(InMemoryContextStore):

    def __init__(self, folder_path: str, contexts: Dict[str, Context]):
        super().__init__()
        self._folder_path = folder_path
        self._contexts = contexts

    @staticmethod
    def load(cls, folder_path: str) -> "ContextStore":
        contexts = {}
        for root, _, files in os.walk(folder_path):
            for file in files:
                file_path = os.path.join(root, file)
                context = Context.load(file_path)
                contexts[context.id] = context

        return cls(folder_path, contexts)

    def save(self, context: Context) -> None:
        super().save()
        context.save(os.path.join(self._folder_path, context.id))
