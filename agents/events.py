from typing import Any, Dict, List, Tuple

from agents.context import Event
from agents.llms.llm import Prompt
from agents.tools.types import ToolArguments, ToolResults


class AgentCalled(Event):
    def __init__(self, agent: str, args: ToolArguments):
        super().__init__("agent_called")
        self.agent = agent
        self.data = args

    def __str__(self) -> str:
        args_str = ", ".join(
            f"{arg}={value}" for arg, value in self.data.items()
        )
        return f"{self._get_readable_timestamp()} - {self.agent}({args_str})"


class AgentPrompt(Event):
    def __init__(self, agent: str, prompt: Prompt):
        super().__init__("agent_prompt")
        self.agent = agent
        self.data = prompt

    def __str__(self) -> str:
        return (
            f"{self._get_readable_timestamp()} - {self.agent} prepared prompt:\n"
            f"{self.data}"
        )


class AgentLLMResponse(Event):
    def __init__(self, agent: str, response: str):
        super().__init__("agent_llm_response")
        self.agent = agent
        self.data = response

    def __str__(self) -> str:
        return (
            f"{self._get_readable_timestamp()} - {self.agent} received LLM response:\n"
            f"{self.data}"
        )


class AgentReturn(Event):
    def __init__(self, agent: str, result: Any):
        super().__init__("agent_return")
        self.agent = agent
        self.data = result

    def __str__(self) -> str:
        return (
            f"{self._get_readable_timestamp()} - {self.agent} returned:\n"
            f"{self.data}"
        )


class AgentLLMCalled(Event):
    def __init__(self, agent: str):
        super().__init__("agent_llm_called")
        self.data = agent

    def __str__(self) -> str:
        return f"{self._get_readable_timestamp()} - {self.data} LLM called"


class AgentBackendCalled(Event):
    def __init__(self, agent: str, args: ToolArguments):
        super().__init__("agent_backend_called")
        self.agent = agent
        self.args = args
        self.data = {
            "agent": agent,
            "args": args,
        }

    def __str__(self) -> str:
        return (
            f"{self._get_readable_timestamp()} - {self.agent} backend called:\n"
            f"{self.args}"
        )


class AgentToolCalls(Event):
    def __init__(self, agent: str, tool_calls: ToolResults):
        super().__init__("agent_tool_calls")
        self.agent = agent
        self.tool_calls = tool_calls

        self.data = {
            "agent": agent,
            "tool_calls": tool_calls,
        }

    def __str__(self) -> str:
        tool_calls_str = "\n".join(
            [f"{tool.name}({tool.args})" for tool in self.tool_calls]
        )
        return (
            f"{self._get_readable_timestamp()} - {self.agent} tool calls:\n"
            f"{tool_calls_str}"
        )


class AgentBackendStep(Event):
    def __init__(self, agent: str, step: int):
        super().__init__("agent_step")
        self.agent = agent
        self.step = step

        self.data = {
            "agent": agent,
            "step": step,
        }

    def __str__(self) -> str:
        return (
            f"{self._get_readable_timestamp()} - {self.agent} step {self.step}"
        )
