from typing import Any, Dict

from arkaine.utils.resource import Resource


class Finding:

    def __init__(self, resource: Resource, summary: str, content: str):
        self.source = f"{resource.name} - {resource.source}"
        self.summary = summary
        self.content = content
        self.resource = resource

    def to_json(self):
        return {
            "content": self.content,
            "summary": self.summary,
            "resource": self.resource.to_json(),
        }

    @classmethod
    def from_json(cls, json: Dict[str, Any]):
        return cls(
            Resource.from_json(json["resource"]),
            json["summary"],
            json["content"],
        )

    def __str__(self):
        resource = f"{self.resource.name} - {self.resource.source}"
        return f"{resource}\n{self.summary}\n{self.content}"

    def __repr__(self):
        return self.__str__()
