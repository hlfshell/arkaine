from __future__ import annotations

from abc import ABC, abstractmethod
from concurrent.futures import Future, wait
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
    ):
        super().__init__()
        self.llm = llm
        self.tools: Dict[str, Tool] = {}
        for tool in tools:
            self.tools[tool.name] = tool

        self.max_simultaneous_tool_calls = max_simultaneous_tools
        self.initial_state = initial_state
        self.process_answer = process_answer

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
    def tool_results_to_prompts(
        self, context: Context, prompt: Prompt, results: ToolResults
    ) -> List[Prompt]:
        """
        tool_results_to_prompts is called upon the return of each invoked tool
        by the backend. It is passed the current context and the results of
        each tool. results is a ToolResults type - A list of tuples, wherein
        each tuple is the name of the function being called, the ToolArguments
        (a dict w/ str key and Any value being passed to the function), and the
        return of that tool (Any). This is done because any given tool can be
        invoked multiple times by the model in a single iteration.

        If the tool threw an exception, it is returned as the result. How you
        handle that result is up to the implementer of the backend. It is
        recommended, however, that you handle InvalidArgumentException and
        ToolNotFoundException as they are essentially caused by mistakes of the
        LLM, and you can use this to better prompt/guide the LLM towards
        utilizing the tools correctly.
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

        # Build prompt
        prompt = self.prepare_prompt(context, **args)

        steps = 0

        while True:
            steps += 1
            context.broadcast(AgentBackendStep(steps))

            if max_steps and steps > max_steps:
                raise Exception("too many steps")

            response = self.query_model(context, prompt)

            tool_calls = self.parse_for_tool_calls(
                context,
                response,
                stop_at_first_tool,
            )

            result = self.parse_for_result(context, response)

            if result:
                if self.process_answer:
                    return self.process_answer(result)
                else:
                    return result
            elif len(tool_calls) > 0:
                context.broadcast(AgentToolCalls(tool_calls))
                tool_results = self.call_tools(context, tool_calls)
                prompt = self.tool_results_to_prompts(
                    context, prompt, tool_results
                )


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
