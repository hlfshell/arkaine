from typing import Any, Dict, List, Tuple

from agents.context import Event
from agents.llms.llm import Prompt
from agents.tools.types import ToolArguments, ToolResults


class AgentCalled(Event):
    def __init__(self, agent: str, args: ToolArguments):
        super().__init__("agent_called")
        self.agent = agent
        self.args = args

    def __str__(self) -> str:
        out = f"{self.agent}("
        for arg, value in self.args.items():
            out += ", ".join(f"{arg}={value}")
        out += f") @ {self._get_readable_timestamp()}"
        return out


class AgentPrompt(Event):
    def __init__(self, agent: str, prompt: Prompt):
        super().__init__("agent_prompt")
        self.agent = agent
        self.prompt = prompt

    def __str__(self) -> str:
        return (
            f"{self.agent} prepared prompt @ {self._get_readable_timestamp()}:"
            f"\n{self.prompt}"
        )


class AgentLLMResponse(Event):
    def __init__(self, agent: str, response: str):
        super().__init__("agent_llm_response")
        self.agent = agent
        self.response = response

    def __str__(self) -> str:
        return (
            f"{self.agent} received LLM response @ "
            f"{self._get_readable_timestamp()}:\n{self.response}"
        )


class AgentReturn(Event):
    def __init__(self, agent: str, result: Any):
        super().__init__("agent_return")
        self.agent = agent
        self.result = result

    def __str__(self) -> str:
        return (
            f"{self.agent} returned @ "
            f"{self._get_readable_timestamp()}:\n{self.result}"
        )


class AgentLLMCalled(Event):
    def __init__(self, agent: str):
        super().__init__("agent_llm_called")
        self.agent = agent

    def __str__(self) -> str:
        return f"{self.agent} LLM called @ {self._get_readable_timestamp()}"


class AgentBackendCalled(Event):
    def __init__(self, agent: str, args: ToolArguments):
        super().__init__("agent_backend_called")
        self.agent = agent
        self.args = args

    def __str__(self) -> str:
        return (
            f"{self.agent} backend called @ "
            f"{self._get_readable_timestamp()}:\n{self.args}"
        )


class AgentToolCalls(Event):
    def __init__(self, agent: str, tool_calls: ToolResults):
        super().__init__("agent_tool_calls")
        self.agent = agent
        self.tool_calls = tool_calls

    def __str__(self) -> str:
        out = f"{self.agent} tool calls @ {self._get_readable_timestamp()}:\n"

        out += "\n".join(
            [f"{tool.name}({tool.args})" for tool in self.tool_calls]
        )
        return out


class AgentStep(Event):
    def __init__(self, agent: str, step: int):
        super().__init__("agent_step")
        self.agent = agent
        self.step = step

    def __str__(self) -> str:
        return (
            f"{self.agent} step @ "
            f"{self._get_readable_timestamp()}: {self.step}"
        )
