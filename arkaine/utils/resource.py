from abc import ABC, abstractmethod
from uuid import uuid4
from typing import Optional


class Resource:
    def __init__(
        self,
        source: str,
        name: str,
        type: str,
        description: str,
        id: Optional[str] = None,
    ):
        self.id = id if id else str(uuid4())
        self.name = name
        self.source = source
        self.type = type
        self.description = description

    def to_json(self):
        return {
            "id": self.id,
            "name": self.name,
            "source": self.source,
            "type": self.type,
            "description": self.description,
        }

    @classmethod
    def from_json(cls, json: dict):
        return cls(
            json["source"],
            json["name"],
            json["type"],
            json["description"],
            json["id"],
        )

    def __str__(self):
        return (
            f"ID: {self.id}\n"
            f"NAME: {self.name}\n"
            f"TYPE: {self.type}\n"
            f"SOURCE: {self.source}\n"
            f"DESCRIPTION: {self.description}"
        )

    def __repr__(self):
        return self.__str__()
