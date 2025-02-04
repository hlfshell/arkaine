from typing import Any, Dict, Protocol, runtime_checkable


@runtime_checkable
class Attachable(Protocol):
    """
    Protocol class defining the interface for objects that can be attached
    to a Context. This allows for duck typing of tools and LLMs that can
    be attached to contexts.
    """

    @property
    def id(self) -> str:
        """Unique identifier for the attachable object"""
        ...

    @property
    def name(self) -> str:
        """Human-readable name for the attachable object"""
        ...

    @property
    def type(self) -> str:
        """Type of the attachable object"""
        ...

    @property
    def to_json(self) -> Dict[str, Any]:
        """JSON representation of the attachable object"""
        ...
