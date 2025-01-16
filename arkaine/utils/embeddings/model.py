import os
from abc import ABC, abstractmethod
from typing import List, Optional, Union

import ollama
import openai


class EmbeddingModel(ABC):

    def __init__(self, model: str):
        super().__init__()

    @abstractmethod
    def embed(self, text: Union[str, List[str]]) -> List[List[float]]:
        pass


class OllamaEmbeddingModel(EmbeddingModel):

    def __init__(self, model: str = "all-minilm:latest"):
        self.__embedding_model = model
        super().__init__()

    def embed(self, text: Union[str, List[str]]) -> List[List[float]]:
        vectors: List[List[float]] = []

        if isinstance(text, str):
            text = [text]

        for t in text:
            vectors.append(
                ollama.embeddings(model=self.__embedding_model__, prompt=text)[
                    "embedding"
                ]
            )

        return vectors


class OpenAIEmbeddingModel(EmbeddingModel):

    def __init__(
        self,
        model: str = "text-embedding-ada-002",
        api_key: Optional[str] = None,
    ):
        self.__embedding_model = model
        api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.__client = openai.Client(api_key=api_key)

        super().__init__()

    def embed(self, text: Union[str, List[str]]) -> List[List[float]]:
        if isinstance(text, str):
            text = [text]

        response = self.__client.embeddings.create(
            input=text,
            model=self.__embedding_model,
        )
        return response.data[0].embedding
