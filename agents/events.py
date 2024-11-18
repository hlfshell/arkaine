from typing import Any

from agents.llms.llm import Prompt
from agents.tools.tool import Event
from agents.tools.types import ToolArguments, ToolResults


class AgentCalled(Event):
    def __init__(self, args: ToolArguments):
        super().__init__("agent_called")
        self.data = args

    def __str__(self) -> str:
        args_str = ", ".join(
            f"{arg}={value}" for arg, value in self.data.items()
        )
        return f"{self._get_readable_timestamp()}({args_str})"


class AgentPrompt(Event):
    def __init__(self, prompt: Prompt):
        super().__init__("agent_prompt")
        self.data = prompt

    def __str__(self) -> str:
        return (
            f"{self._get_readable_timestamp()} prepared "
            f"prompt:\n{self.data}"
        )


class AgentLLMResponse(Event):
    def __init__(self, response: str):
        super().__init__("agent_llm_response")
        self.data = response

    def __str__(self) -> str:
        return (
            f"{self._get_readable_timestamp()} received "
            f"LLM response:\n{self.data}"
        )


class AgentReturn(Event):
    def __init__(self, result: Any):
        super().__init__("agent_return")
        self.data = result

    def __str__(self) -> str:
        return f"{self._get_readable_timestamp()} returned:\n" f"{self.data}"


class AgentLLMCalled(Event):
    def __init__(self):
        super().__init__("agent_llm_called")

    def __str__(self) -> str:
        return f"{self._get_readable_timestamp()} LLM model called"


class AgentToolCalls(Event):
    def __init__(self, tool_calls: ToolResults):
        super().__init__("agent_tool_calls")
        self.data = tool_calls

    def __str__(self) -> str:
        tool_calls_str = "\n".join(
            [f"{tool.name}({tool.args})" for tool in self.data]
        )
        return (
            f"{self._get_readable_timestamp()} tool calls:\n"
            f"{tool_calls_str}"
        )


class AgentBackendStep(Event):
    def __init__(self, step: int):
        super().__init__("agent_step")
        self.step = step

        self.data = {
            "step": step,
        }

    def __str__(self) -> str:
        return f"{self._get_readable_timestamp()} step {self.step}"
