from __future__ import annotations

from abc import ABC, abstractmethod
from concurrent.futures import Future, wait
from time import time
from typing import Any, Callable, Dict, List, Optional, Tuple

from arkaine.events import (
    AgentBackendStep,
    AgentLLMResponse,
    AgentPrompt,
    AgentToolCalls,
)
from arkaine.llms.llm import LLM, Prompt
from arkaine.tools.context import Context
from arkaine.tools.tool import Tool
from arkaine.tools.types import ToolArguments, ToolCalls, ToolResults


class Backend(ABC):

    def __init__(
        self,
        llm: LLM,
        tools: List[Tool],
        max_simultaneous_tools: int = 1,
        initial_state: Dict[str, Any] = {},
        process_answer: Optional[Callable[[Any], Any]] = None,
        max_steps: Optional[int] = None,
        max_time: Optional[int] = None,
    ):
        super().__init__()
        self.llm = llm
        self.tools: Dict[str, Tool] = {}
        for tool in tools:
            self.tools[tool.name] = tool

        self.max_simultaneous_tool_calls = max_simultaneous_tools
        self.initial_state = initial_state
        self.process_answer = process_answer
        self.max_steps = max_steps
        self.max_time = max_time

    @abstractmethod
    def parse_for_tool_calls(
        self, context: Context, text: str, stop_at_first_tool: bool = False
    ) -> ToolCalls:
        """
        parse_for_tool_calls is called after each model iteration if any tools
        are provided to the backend. The goal of parse_for_tool_calls is to
        parse the raw output of the model and detect every tool call and their
        respective arguments as needed for the tools.

        The return of the function is a list of tuples, where the first item in
        each tuple is the name of the function, and the second is a
        ToolArguments parameter (a dict of str keys and Any values). The list
        is utilized because it is possible that A) ordering of the tools
        matters for a given application and B) a given tool may be called
        multiple times by the model.
        """
        pass

    @abstractmethod
    def parse_for_result(self, context: Context, text: str) -> Optional[Any]:
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
    def format_tool_results(
        self, context: Context, results: ToolResults
    ) -> List[str]:
        """
        format_tool_results is called upon the return of each invoked tool
        by the backend. It is passed the current context and the results of
        each tool. results is a ToolResults type - A list of tuples, wherein
        each tuple is the name of the function being called, the ToolArguments
        """
        pass

    @abstractmethod
    def prepare_prompt(self, context: Context, **kwargs) -> Prompt:
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
        if tool.tname in self.tools:
            return
        self.tools[tool.tname] = tool

    def call_tools(
        self, context: Context, calls: List[Tuple[str, ToolArguments]]
    ) -> ToolResults:
        results: List[Any] = [None] * len(calls)
        futures: List[Future] = []
        for idx, (tool, args) in enumerate(calls):
            if tool not in self.tools:
                results[idx] = (tool, args, ToolNotFoundException(tool, args))
                continue

            ctx = self.tools[tool].async_call(context, args)
            futures.append(ctx.future())

        wait(futures)

        for idx, future in enumerate(futures):
            try:
                results[idx] = (calls[idx][0], calls[idx][1], future.result())
            except Exception as e:
                results[idx] = (calls[idx][0], calls[idx][1], e)

        return results

    def query_model(self, context: Context, prompt: Prompt) -> str:
        return self.llm(context, prompt)

    def estimate_tokens(self, prompt: Prompt) -> int:
        return self.llm.estimate_tokens(prompt)

    def _initialize_state(self, context: Context):
        state = self.initial_state.copy()
        for key, value in state.items():
            context[key] = value

    def invoke(
        self,
        context: Context,
        args: Dict[str, Any],
        max_steps: Optional[int] = None,
        stop_at_first_tool: bool = False,
    ) -> str:
        self._initialize_state(context)

        tool_results: List[Tuple[str, ToolResults]] = []
        context.init("steps", 0)
        context.init("start_time", time())
        context.init("responses", [])

        while True:
            elapsed_time = time() - context["start_time"]
            if self.max_time and elapsed_time > self.max_time:
                context["time_elapsed"] = elapsed_time
                raise MaxTimeExceededException(self.max_time, elapsed_time)

            context["prompt"] = self.prepare_prompt(
                context, tool_results=tool_results, **args
            )

            if self.max_steps and context["steps"] + 1 > self.max_steps:
                context["time_elapsed"] = elapsed_time
                raise MaxStepsExceededException(
                    self.max_steps, context["steps"]
                )

            context.increment("steps")
            context.broadcast(AgentBackendStep(context["steps"]))

            if max_steps and context["steps"] > max_steps:
                context["time_elapsed"] = elapsed_time
                raise MaxStepsExceededException(context["steps"])

            response = self.query_model(context, context["prompt"])
            context.append("responses", response)

            result = self.parse_for_result(context, response)

            if result:
                if self.process_answer:
                    context["time_elapsed"] = elapsed_time
                    return self.process_answer(result)
                else:
                    context["time_elapsed"] = elapsed_time
                    return result

            tool_calls = self.parse_for_tool_calls(
                context,
                response,
                stop_at_first_tool,
            )
            if len(tool_calls) > 0:
                context.broadcast(AgentToolCalls(tool_calls))
                tool_results = self.call_tools(context, tool_calls)
            else:
                tool_results = [(None, {}, None)]


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
        max_steps: int,
        steps: int,
    ):
        self.__max_steps = max_steps
        self.__steps = steps

    def __str__(self) -> str:
        return f"exceeded max steps ({self.__steps} > {self.__max_steps})"


class MaxTimeExceededException(Exception):
    def __init__(self, max_time: int, elapsed_time: int):
        self.__max_time = max_time
        self.__elapsed_time = elapsed_time

    def __str__(self) -> str:
        return (
            f"exceeded max time ({self.__elapsed_time} seconds > "
            f"{self.__max_time} seconds)"
        )
