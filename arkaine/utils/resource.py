from typing import Callable, Optional, Union
from uuid import uuid4


class Resource:
    def __init__(
        self,
        source: str,
        name: str,
        type: str,
        description: str,
        content: Union[str, Callable[[], str]],
        id: Optional[str] = None,
    ):
        self.id = id if id else str(uuid4())
        self.name = name
        self.source = source
        self.type = type
        self.description = description
        self.__content = content

    @property
    def content(self):
        if callable(self.__content):
            return self.__content()
        return self.__content

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

    def __eq__(self, value: object) -> bool:
        if not isinstance(value, Resource):
            return False
        return self.id == value.id

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

    def __getstate__(self):
        # Ensure content is evaluated before pickling
        state = self.__dict__.copy()
        if callable(state["_Resource__content"]):
            try:
                state["_Resource__content"] = state["_Resource__content"]()
            except Exception as e:
                print(f"Error evaluating content: {e}")
                state["_Resource__content"] = ""
        return state
