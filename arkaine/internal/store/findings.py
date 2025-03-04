from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, Optional

from arkaine.toolbox.research.finding import Finding
from arkaine.internal.store.query import Query, Check
from typing import Union


class FindingStore(ABC):
    @abstractmethod
    def save(self, finding: Finding) -> None:
        pass

    @abstractmethod
    def delete(self, finding: Finding) -> None:
        pass

    @abstractmethod
    def get(self, id: str) -> Finding:
        pass

    @abstractmethod
    def query(
        self,
        query: Union[Query, List[Query], Check, List[Check]],
        limit: Optional[int] = None,
        embedding: Optional[List[float]] = None,
    ) -> List[Finding]:
        pass
