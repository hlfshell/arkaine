from typing import Any

from agents.context import Event
from agents.tools.types import ToolArguments


class ToolCalled(Event):
    def __init__(self, tool: str, args: ToolArguments):
        super().__init__("tool_called")

        self.tool = tool
        self.args = args

        self.data = {
            "tool": tool,
            "args": args,
        }

    def __str__(self) -> str:
        out = f"{self._get_readable_timestamp()} - {self.tool}("
        for arg, value in self.args.items():
            out += ", ".join(f"{arg}={value}")
        out += ")"
        return out


class ToolStart(Event):
    def __init__(self, tool: str):
        super().__init__("tool_start")

        self.data = tool

    def __str__(self) -> str:
        return f"{self._get_readable_timestamp()} - {self.tool} started"


class ToolReturn(Event):
    def __init__(self, tool: str, result: Any):
        super().__init__("tool_return", result)

        self.tool = tool
        self.result = result

        self.data = {
            "tool": tool,
            "result": result,
        }

    def __str__(self) -> str:
        return (
            f"{self._get_readable_timestamp()} - {self.tool} returned:\n"
            f"{self.result}"
        )
