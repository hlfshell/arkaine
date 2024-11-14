from typing import Any

from agents.context import Event
from agents.tools.types import ToolArguments


class ToolCalled(Event):
    def __init__(self, tool: str, args: ToolArguments):
        super().__init__("tool_called")

        self.tool = tool
        self.args = args

    def __str__(self) -> str:
        out = f"{self.tool}("
        for arg, value in self._data.items():
            out += ", ".join(f"{arg}={value}")
        out += f") @ {self._get_readable_timestamp()}"

        return out


class ToolStart(Event):
    def __init__(self, tool: str):
        super().__init__("tool_start")

        self.tool = tool

    def __str__(self) -> str:
        return f"{self.tool} started @ {self._get_readable_timestamp()}"


class ToolReturn(Event):
    def __init__(self, tool: str, result: Any):
        super().__init__("tool_return", result)

        self.tool = tool
        self.result = result

    def __str__(self) -> str:
        return (
            f"{self.tool} returned @ {self._get_readable_timestamp()}:\n"
            f"{self.result}"
        )
