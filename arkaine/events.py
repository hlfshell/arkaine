from typing import List, Tuple

from arkaine.llms.llm import Prompt
from arkaine.tools.events import Event
from arkaine.tools.types import ToolArguments


class AgentPrompt(Event):
    def __init__(self, prompt: Prompt):
        super().__init__(AgentPrompt, prompt)

    @classmethod
    def type(self) -> str:
        return "agent_prompt"

    def __str__(self) -> str:
        return (
            f"{self._get_readable_timestamp()} prepared "
            f"prompt:\n{self.data}"
        )


class AgentLLMResponse(Event):
    def __init__(self, response: str):
        super().__init__(AgentLLMResponse, response)

    @classmethod
    def type(self) -> str:
        return "agent_llm_response"

    def __str__(self) -> str:
        return (
            f"{self._get_readable_timestamp()} received "
            f"LLM response:\n{self.data}"
        )


class AgentLLMCalled(Event):
    def __init__(self):
        super().__init__(AgentLLMCalled)

    @classmethod
    def type(self) -> str:
        return "agent_llm_called"

    def __str__(self) -> str:
        return f"{self._get_readable_timestamp()} LLM model called"


class AgentToolCalls(Event):
    def __init__(self, tool_calls: List[Tuple[str, ToolArguments]]):
        super().__init__(AgentToolCalls, tool_calls)

    @classmethod
    def type(self) -> str:
        return "agent_tool_calls"

    def __str__(self) -> str:
        tool_calls_str = ""
        for tool_name, tool_args in self.data:
            arg_str = ", ".join(
                f"{arg}={value}" for arg, value in tool_args.items()
            )
            tool_calls_str += f"- {tool_name}({arg_str})\n"

        return (
            f"{self._get_readable_timestamp()} tool calls:\n"
            f"{tool_calls_str}"
        )


class AgentBackendStep(Event):
    def __init__(self, step: int):
        super().__init__(AgentBackendStep)
        self.step = step

        self.data = {
            "step": step,
        }

    @classmethod
    def type(self) -> str:
        return "agent_step"

    def __str__(self) -> str:
        return f"{self._get_readable_timestamp()} step {self.step}"
