from typing import Any, Dict


class Finding:

    def __init__(self, source: str, summary: str, content: str):
        self.source = source
        self.summary = summary
        self.content = content

    def to_json(self):
        return {
            "source": self.source,
            "content": self.content,
            "summary": self.summary,
        }

    @classmethod
    def from_json(cls, json: Dict[str, Any]):
        return cls(json["source"], json["summary"], json["content"])

    def __str__(self):
        return f"{self.source}\n{self.summary}\n{self.content}"

    def __repr__(self):
        return self.__str__()
