from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, List, Optional, Union

from arkaine.internal.store.query import Check, Query

if TYPE_CHECKING:
    from arkaine.tools.context import Context


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


class ContextStore(ABC):
    """
    The goal of a context store is to provide a way to store, query for, and
    retrieve contexts over several executions.
    """

    def __init__(self):
        super().__init__()

    @abstractmethod
    def get(self, id: str) -> Optional[Context]:
        """
        get_context retrieves a context from the store by its id.

        Args:
            id: The unique identifier of the context

        Returns:
            Context: The context if found, None otherwise
        """
        pass

    @abstractmethod
    def query(
        self,
        query: Union[Query, List[Query], Check, List[Check]],
        limit: Optional[int] = None,
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
