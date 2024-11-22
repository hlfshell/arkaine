from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Tuple

from agents.events import (
    AgentBackendStep,
    AgentLLMResponse,
    AgentPrompt,
    AgentToolCalls,
)
from agents.llms.llm import LLM, Prompt
from agents.tools.tool import Context, Tool
from agents.tools.types import ToolArguments, ToolResults


class BaseBackend(ABC):

    def __init__(
        self, llm: LLM, tools: List[Tool], max_simultaneous_tools: int = 1
    ):
        super().__init__()
        self.llm = llm
        self.tools: Dict[str, Tool] = {}
        for tool in tools:
            self.tools[tool.name] = tool

        self.max_simultaneous_tool_calls = max_simultaneous_tools

    @abstractmethod
    def parse_for_tool_calls(
        self, text: str, stop_at_first_tool: bool = False
    ) -> List[Tuple[str, ToolArguments]]:
        """
        parse_for_tool_calls is called after each model iteration if any tools
        are provided to the backend. The goal of parse_for_tool_calls is to
        parse the raw output of the model and detect every tool call and their
        respective arguments as needed for the tools.

        The return of the function is a list of tuples, where the first item in
        each tuple is the name of the function, and the second is a
        ToolArguments parameter (a dict of str keys and Any values). The list
        is utilized because it is possible that A) ordering of the tools
        matters for a given application abd B) a given tool may be called
        multiple times for by the model.
        """
        pass

    @abstractmethod
    def parse_for_result(self, text: str) -> Optional[Any]:
        """
        parse_for_result is called after the model produces an output that
        contains no tool calls to operate on. If no output is necessary, merely
        return None. If output is expected but not found, it is on the
        implementor to raise an Exception or deal with it.

        Once parse_for_results is called and returns, the invocation of the
        backend is finished and returned.
        """
        pass

    @abstractmethod
    def tool_results_to_prompts(
        self, prompt: Prompt, results: ToolResults
    ) -> List[Prompt]:
        """
        tool_results_to_prompts is called upon the return of each invoked tool
        by the backend. It is passed the current context and the results of
        each tool. results is a ToolResults type - A list of tuples, wherein
        each tuple is the name of the function being called, the ToolArguments
        (a dict w/ str key and Any value being passed to the function), and the
        return of that tool (Any). This is done because any given tool can be
        invoked multiple times by the model in a single iteration.

        The return is an updated context
        """
        pass

    @abstractmethod
    def prepare_prompt(self, **kwargs) -> Prompt:
        """
        prepare_prompt prepares the initial prompt to tell it what to do. This
        is often the explanation of what the agent is and what its current task
        is. Utilize keyword arguments to
        """
        pass

    def add_tool(self, tool: Tool):
        """
        Adds a tool to the backend if it does not already exist.
        """
        if tool.name in self.tools:
            return
        self.tools[tool.name] = tool

    def call_tools(
        self, context: Context, calls: List[Tuple[str, ToolArguments]]
    ) -> ToolResults:
        # TODO - parallelize it!
        results: ToolResults = []
        for tool, args in calls:
            if tool not in self.tools:
                raise ToolNotFoundException(tool, args)
            ctx = context.child_context(self.tools[tool])
            results.append((tool, args, self.tools[tool](ctx, **args)))

        return results

    def query_model(self, prompt: Prompt) -> str:
        return self.llm.completion(prompt)

    def invoke(
        self,
        context: Context,
        args: Dict[str, Any],
        max_steps: Optional[int] = None,
        stop_at_first_tool: bool = False,
    ) -> str:
        # Build prompt
        prompt = self.prepare_prompt(**args)
        context.broadcast(AgentPrompt(prompt))

        steps = 0

        while True:
            steps += 1
            context.broadcast(AgentBackendStep(steps))

            if max_steps and steps > max_steps:
                raise Exception("too many steps")

            response = self.query_model(prompt)
            context.broadcast(AgentLLMResponse(response))

            tool_calls = self.parse_for_tool_calls(
                response,
                stop_at_first_tool,
            )

            if len(tool_calls) > 0:
                context.broadcast(AgentToolCalls(tool_calls))
                tool_results = self.call_tools(context, tool_calls)
                prompt = self.tool_results_to_prompts(prompt, tool_results)
            else:
                # No tool calls means we should have a result
                # TODO - handle a failure to produce
                # tool calls
                return self.parse_for_result(response)


class ToolNotFoundException(Exception):
    def __init__(self, name: str, arguments: ToolArguments):
        self.__name = name
        self.__arguments = arguments

    def __str__(self) -> str:
        out = f"tool not found - {self.__name}("
        out += ", ".join(
            [arg + "=" + value for arg, value in self.__arguments.items()]
        )
        out += ")"

        return out


class MaxStepsExceededException(Exception):

    def __init__(
        self,
        steps: int,
    ):
        self.__steps = steps

    def __str__(self) -> str:
        return f"exceeded max steps ({self.__steps})"
