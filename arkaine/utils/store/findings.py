import os
from threading import Lock
from typing import List, Optional, Union

from arkaine.internal.store.findings import FindingStore
from arkaine.internal.store.query import Check, Query
from arkaine.toolbox.research.finding import Finding
from arkaine.utils.embeddings.distance import cosine_distance
from arkaine.utils.embeddings.model import EmbeddingModel


class InMemoryFindingStore(FindingStore):
    def __init__(self, embedding_model: Optional[EmbeddingModel] = None):
        super().__init__()
        self.findings = {}
        self._lock = Lock()
        self._embedding_model = embedding_model

    def save(self, finding: Finding):
        if finding.embedding is None and self._embedding_model is not None:
            finding.embedding = self._embedding_model.embed(finding.content)
        with self._lock:
            self.findings[finding.id] = finding

    def delete(self, finding: Finding):
        with self._lock:
            del self.findings[finding.id]

    def get(self, id: str) -> Finding:
        with self._lock:
            return self.findings[id]

    def query(
        self,
        query: Union[Query, List[Query], Check, List[Check]],
        limit: Optional[int] = None,
        embedding: Optional[List[float]] = None,
    ) -> List[Finding]:
        if isinstance(query, List):
            q = Query()
            for i in query:
                q += i
            query = q
        elif isinstance(query, Check):
            query = Query([query])

        with self._lock:
            findings = [
                finding for finding in self.findings.values() if query(finding)
            ]

        if embedding is not None:
            # Sort findings by cosine similarity (not distance), putting None embeddings at the
            # end. Higher cosine similarity values indicate more similar vectors.
            findings.sort(
                key=lambda f: (
                    -cosine_distance(embedding, f.embedding)
                    if f.embedding is not None
                    else float("-inf")
                )
            )

        if limit is not None:
            findings = findings[:limit]

        return findings

    def __enter__(self) -> FindingStore:
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        pass


class FileFindingStore(InMemoryFindingStore):
    def __init__(
        self, folder_path: str, embedding_model: Optional[EmbeddingModel] = None
    ):
        super().__init__(embedding_model)
        self.folder_path = folder_path

    @staticmethod
    def load(cls, folder_path: str) -> FindingStore:
        store = cls(folder_path)
        store.reload()
        return store

    def reload(self):
        for file in os.listdir(self.folder_path):
            with open(os.path.join(self.folder_path, file), "r") as f:
                self.findings[file] = Finding.load(f)

    def write(self):
        with self._lock:
            for finding in self.findings.values():
                with open(os.path.join(self.folder_path, finding.id), "w") as f:
                    finding.write(f)
            self.findings[finding.id] = finding


class GlobalFindingStore(FindingStore):
    __store: FindingStore = None
    __lock = Lock()

    def __init__(self):
        raise ValueError("GlobalFindingStore cannot be instantiated")

    @classmethod
    def set_store(cls, store: Optional[FindingStore] = None):
        with cls.__lock:
            if cls.__store is not None:
                raise ValueError("Store already set")
            cls.__store = store if store is not None else InMemoryFindingStore()

    @classmethod
    def get_store(cls) -> FindingStore:
        with cls.__lock:
            if cls.__store is None:
                cls.set_store()
            return cls.__store
