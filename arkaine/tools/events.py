from __future__ import annotations
import traceback
from abc import abstractmethod
from datetime import datetime, timezone
from time import time
from typing import Any, Type, Union

from arkaine.internal.to_json import recursive_to_json
from arkaine.tools.types import ToolArguments


class Event:
    """
    Event are events that can occur throughout execution of the agent,
    and are thus bubbled up through the chain of the context.
    """

    # Keep Event class here since it's the base class

    def __init__(self, event_type: Union[str, Type[Event]], data: Any = None):
        self._event_type = event_type
        self.data = data
        self._timestamp = time()

    @classmethod
    @abstractmethod
    def type(self) -> str:
        return "event"

    @property
    def timestamp(self) -> float:
        return self._timestamp

    def _get_readable_timestamp(self) -> str:
        return datetime.fromtimestamp(
            self._timestamp, tz=timezone.utc
        ).strftime("%Y-%m-%d %H:%M:%S UTC")

    def __str__(self) -> str:
        out = f"{self._get_readable_timestamp()}: {self._event_type}"
        if self.data:
            out += f":\n{self.data}"
        return out

    def to_json(self) -> dict:
        """Convert Event to a JSON-serializable dictionary."""
        data = recursive_to_json(self.data)

        return {
            "type": self._event_type,
            "timestamp": self._timestamp,
            "data": data,
        }


class ToolCalled(Event):
    def __init__(self, args: ToolArguments):
        super().__init__(ToolCalled, args)

    @classmethod
    def type(self) -> str:
        return "tool_called"

    def __str__(self) -> str:
        args_str = ", ".join(
            f"{arg}={value}" for arg, value in self.data.items()
        )
        return f"{self._get_readable_timestamp()} ({args_str!s})"


class ToolStart(Event):
    def __init__(self, tool: str):
        super().__init__(ToolStart, tool)

    @classmethod
    def type(self) -> str:
        return "tool_start"

    def __str__(self) -> str:
        return f"{self._get_readable_timestamp()} - {self.data} started"


class ToolReturn(Event):
    def __init__(self, result: Any):
        super().__init__(ToolReturn, result)

    @classmethod
    def type(self) -> str:
        return "tool_return"

    def __str__(self) -> str:
        return f"{self._get_readable_timestamp()} returned:\n" f"{self.data}"


class ToolException(Event):
    def __init__(self, exception: Exception):
        super().__init__(ToolException, exception)

    @classmethod
    def type(self) -> str:
        return "tool_exception"

    def __str__(self) -> str:
        out = f"{self._get_readable_timestamp()}: tool_exception -"
        if self.data:
            e: Exception = self.data

            # Grab the stack trace from the Exception and add it to the output
            out += f"\n{e}\n\n"

            out += "".join(
                traceback.format_exception(type(e), e, e.__traceback__)
            )

        return out

    def to_json(self) -> dict:
        return {
            "type": self._event_type,
            "timestamp": self._timestamp,
            "data": str(self),
        }


class ChildContextCreated(Event):
    def __init__(self, parent: str, child: str):
        super().__init__(
            ChildContextCreated, {"parent": parent, "child": child}
        )

    @classmethod
    def type(self) -> str:
        return "child_context_created"

    def __str__(self) -> str:
        out = f"{self._get_readable_timestamp()}: context_created"
        if self.data:
            out += f":\n{self.data}"
        return out


class ContextUpdate(Event):
    def __init__(self, **kwargs):
        data = {
            **kwargs,
        }
        super().__init__(ContextUpdate, data)

    @classmethod
    def type(self) -> str:
        return "context_update"

    def __str__(self) -> str:
        out = f"{self._get_readable_timestamp()}: context_update"
        if self.data:
            out += f":\n{self.data}"
        return out
