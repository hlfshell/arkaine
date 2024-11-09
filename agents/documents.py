import math
import re
from typing import List, Optional, Tuple, Union

import ollama


def generate_embedding(text: str):
    embedding = ollama.embeddings(
        model="avr/sfr-embedding-mistral:q4_k_m", prompt=text
    )
    return embedding["embedding"]


def isolate_sentences(text: str) -> List[str]:
    sentences = []
    current_sentence = ""
    for word in text.split():
        current_sentence += word.strip() + " "
        if word.endswith(".") or word.endswith("?") or word.endswith("!"):
            sentences.append(current_sentence.strip())
            current_sentence = ""

    return sentences


def chunk_text_by_sentences(
    text: str,
    sentences_per: int,
    overlap: int = 0,
    isolate_paragraphs: bool = False,
):
    if isolate_paragraphs:
        paragraphs = re.split(r"\n{2,}", text)
        text = [p.strip() for p in paragraphs if p.strip()]
    else:
        text = [text]

    chunks = []

    for paragraph in text:
        sentences = isolate_sentences(paragraph)
        while len(sentences) > 0:
            chunks.append(" ".join(sentences[0:sentences_per]))
            sentences = sentences[sentences_per + 1 - overlap :]

    return chunks


def cosine_distance(a: List[float], b: List[float]):
    """
    cosine_distance calculates the cosine distance between two vectors, which
    are assumed to be a 1-d array of floats. Returns 1.0 if either vector is
    all zeros.
    """
    if len(a) != len(b):
        raise ValueError("Vectors must have the same length.")

    dot_product = sum(x * y for x, y in zip(a, b))
    magnitude_a = math.sqrt(sum(x**2 for x in a))
    magnitude_b = math.sqrt(sum(x**2 for x in b))

    if magnitude_a == 0 or magnitude_b == 0:
        return 1.0

    cosine_similarity = dot_product / (magnitude_a * magnitude_b)
    cosine_distance = 1 - cosine_similarity
    return cosine_distance


class InMemoryEmbeddingStore:
    """
    InMemoryEmbeddingStore holds a set of text chunks in memory with an
    associated embedding vector. Then, on query, it will return the closest
    embeddings in memory to that vector.

    This is to be used for singular documents or quick ephemeral searches,
    where another more permanent store would be too
    """

    def __init__(self, embedding_model):
        self.__embedding_model__ = embedding_model
        self.__memory__: List[Tuple[str, List[float]]] = []

    def add_text(self, content: Union[str, List[str]]):
        if isinstance(content, str):
            content = [content]

        for text in content:
            self.__memory__.append((text, self.__get_embedding(text)))

    def __measure_distance(self, a: List[float], b: List[float]) -> float:
        return cosine_distance(a, b)

    def __get_embedding(self, text: str) -> List[float]:
        return ollama.embeddings(model="all-minilm:latest", prompt=text)[
            "embedding"
        ]

    def query(
        self,
        query: str,
        top_n: Optional[int] = 10,
    ) -> List[str]:
        query_embedding = self.__get_embedding(query)

        # TODO - make more efficient
        results: List[Tuple[str, float]] = []

        for item in self.__memory__:
            text, embedding = item

            # Find the cosine distance
            distance = self.__measure_distance(query_embedding, embedding)

            results.append([text, distance])

        # Sort the results based on the distance, highest value is best
        results = sorted(results, key=lambda x: x[1], reverse=True)

        if top_n:
            results = results[:top_n]

        out = [x[0] for x in results]

        return out
