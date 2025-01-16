import heapq
from abc import ABC, abstractmethod
from typing import List, Optional, Tuple, Union

from arkaine.utils.embeddings.distance import cosine_distance
from arkaine.utils.embeddings.model import EmbeddingModel


class EmbeddingStore(ABC):

    @abstractmethod
    def add_text(self, content: Union[str, List[str]]) -> List[List[float]]:
        pass

    @abstractmethod
    def query(self, query: str, top_n: Optional[int] = 10) -> List[str]:
        pass


class InMemoryEmbeddingStore(EmbeddingStore):
    """
    InMemoryEmbeddingStore holds a set of text chunks in memory with an
    associated embedding vector. Then, on query, it will return the closest
    embeddings in memory to that vector.

    This is to be used for singular documents or quick ephemeral searches,
    where another more permanent store would be too
    """

    def __init__(self, embedding_model: EmbeddingModel):
        super().__init__()

        self.__embedding_model = embedding_model
        self.__memory__: List[Tuple[str, List[float]]] = []

    def add_text(self, content: Union[str, List[str]]) -> List[List[float]]:
        if isinstance(content, str):
            content = [content]

        embeddings = []

        for text in content:
            embedding = self.get_embedding(text)
            embeddings.append(embedding)
            self.__memory__.append((text, embedding))

        return embeddings

    def __measure_distance(self, a: List[float], b: List[float]) -> float:
        return cosine_distance(a, b)

    def get_embedding(self, text: str) -> List[float]:
        return self.__embedding_model.embed(text)

    def query(
        self,
        query: str,
        top_n: Optional[int] = 10,
    ) -> List[str]:
        query_embedding = self.get_embedding(query)

        # Use a max heap to keep track of top_n results
        # Smaller distances = more similar
        heap = []

        for text, embedding in self.__memory__:
            distance = self.__measure_distance(query_embedding, embedding)

            if top_n:
                if len(heap) < top_n:
                    heapq.heappush(heap, (distance, text))
                else:
                    # Only add if this distance is smaller than our worst
                    # current result
                    if distance < heap[0][0]:
                        heapq.heapreplace(heap, (distance, text))
            else:
                heapq.heappush(heap, (distance, text))

        # Extract results in order (smallest distance first)
        if top_n:
            results = [heapq.heappop(heap) for _ in range(len(heap))]
        else:
            results = heap

        return [text for _, text in results]
