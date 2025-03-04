from typing import Any, Dict, List, Optional
from uuid import uuid4
from typing import Union

from arkaine.utils.resource import Resource


class Finding:

    def __init__(
        self,
        source: Union[str, Resource],
        summary: str,
        content: str,
        id: Optional[str] = None,
        source_id: Optional[str] = None,
        research_id: Optional[str] = None,
        embedding: Optional[List[float]] = None,
    ):
        if isinstance(source, Resource):
            self.source = source.name
            self.source_id = source.id
        else:
            self.source = source
            self.source_id = source_id
        self.summary = summary
        self.content = content
        self.id = id or str(uuid4())
        self.research_id = research_id
        self.embedding = embedding

    def to_json(self):
        return {
            "source": self.source,
            "content": self.content,
            "summary": self.summary,
            "id": self.id,
            "source_id": self.source_id,
            "research_id": self.research_id,
            "embedding": self.embedding,
        }

    @classmethod
    def from_json(cls, json: Dict[str, Any]):
        return cls(
            json["source"],
            json["summary"],
            json["content"],
            json["id"],
            json["source_id"],
            json["research_id"],
            json["embedding"],
        )

    def __str__(self):
        return f"{self.source}\n{self.summary}\n{self.content}"

    def __repr__(self):
        return self.__str__()
