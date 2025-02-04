from __future__ import annotations

import pathlib
import re
from os import path
from typing import Any, Dict, List, Tuple, Union

from arkaine.backends.backend import Backend
from arkaine.backends.common import simple_tool_results_to_prompts
from arkaine.llms.llm import LLM, Prompt
from arkaine.tools.context import Context
from arkaine.tools.tool import Tool
from arkaine.tools.types import ToolArguments, ToolResults
from arkaine.utils.templater import PromptTemplate


class SimpleBackend(Backend):

    def __init__(
        self,
        llm: LLM,
        tools: List[Tool],
        agent_explanation: str,
        max_simultaneous_tools: int = 1,
        initial_state: Dict[str, Any] = {},
    ):
        """
        Creates a simple backend, which simply scans for single line function
        calls such as: function_name(arg1=value1, arg2=value2)

        ...to utilize its tools.

        llm is an LLM provider

        tools is a set of tools the agent has access to

        agent_explanation is a string that explains the agent its purpose when
        solving the task.
        """
        super().__init__(llm, tools, max_simultaneous_tools, initial_state)

        self.agent_explanation = agent_explanation

        self.__templater = PromptTemplate.from_file(
            path.join(
                pathlib.Path(__file__).parent,
                "prompts",
                "simple.prompt",
            )
        )

    def parse_for_result(self, context: Context, text: str) -> str:
        """
        Check to see if the model outputs an answer prepended with Answer: or
        equivalent, strip it.
        """
        pattern = re.compile(r"answer:", re.IGNORECASE)
        match = pattern.search(text)

        if match:
            return text[match.end() :].strip()
        else:
            return text.strip()

    def parse_for_tool_calls(
        self, context: Context, text: str, stop_at_first_tool: bool = False
    ) -> List[Tuple[str, ToolArguments]]:
        """
        By default we will assume that functions follow the form
        function_name(arg1=value, arg2=value)
        ...as a solo line.

        If stop_at_first_tool is enabled, the parser will
        only grab the first tool call. Otherwise it will return
        all tool calls specified.
        """
        tool_calls: List[Tuple[str, ToolArguments]] = {}

        function_names = [tool for tool in self.tools.keys()]
        for line in text.splitlines():
            if line.strip().startswith(tuple(function_names)):

                # Determine if the next character is a (, and has
                # an ending )
                match = re.match(r"(\w+)\((.*)\)$", line.strip())
                if not match:
                    continue

                tool, args_str = match.groups()

                args = self.__parse_arg_string(args_str)

                if stop_at_first_tool:
                    return [(tool, args)]

                tool_calls.append((tool, args))

        return tool_calls

    def tool_results_to_prompts(
        self, context: Context, prompt: Prompt, results: ToolResults
    ) -> List[Prompt]:
        return simple_tool_results_to_prompts(prompt, results)

    def prepare_prompt(self, context: Context, **kwargs) -> Prompt:
        # Create the tools block
        tools_block = ""
        for _, tool in self.tools.items():
            tools_block += f"{tool}\n"

        # Render the prompt
        return self.__templater.render(
            {
                "agent_explanation": self.agent_explanation,
                "tools_block": tools_block,
                "task": kwargs["task"],
            }
        )

    def __parse_arg_string(self, text: str) -> Dict[str, Any]:
        args = {}

        in_quotes = False
        current_key = ""
        current_value = ""

        for char in text:
            if char == "=" and not in_quotes and not current_key:
                current_key = current_value.strip()
                current_value = ""
            elif char == "," and not in_quotes and current_key:
                args[current_key] = self.__attempt_string_to_number(
                    current_value.strip()
                )
                current_key = ""
                current_value = ""
            elif char == '"' or char == "'":
                in_quotes = not in_quotes
            else:
                current_value += char

        if current_key:
            args[current_key] = self.__attempt_string_to_number(
                current_value.strip()
            )

        return args

    def __attempt_string_to_number(
        self, x: str
    ) -> Union[int, float, complex, str]:
        """
        Attempts to convert strings into numbers. Technically you could just
        use complex and avoid redundant checks, but I don't like the complex
        type because when you convert it back to string it gains additional
        notation, which may cause down range issues with LLM agents.

        Returns a the original string if no conversion can be done.
        """
        try:
            return int(x)
        except:  # noqa
            pass
        try:
            return float(x)
        except:  # noqa
            pass
        try:
            return complex(x)
        except:  # noqa
            return x


class InvalidArgumentException(Exception):
    def __init__(
        self,
        tool_name: str,
        missing_required_args: List[str],
        extraneous_args: List[str],
    ):
        self.__tool_name = tool_name
        self.__missing_required_args = missing_required_args
        self.__extraneous_args = extraneous_args

    def __str__(self):
        out = f"Function {self.__tool_name} was improperly called\n"

        if self.__missing_required_args:
            out += (
                "Missing required arguments: "
                + ", ".join(self.__missing_required_args)
                + "\n"
            )
        if self.__extraneous_args:
            out += (
                "Extraneous arguments: "
                + ", ".join(self.__extraneous_args)
                + "\n"
            )

        return out


class ToolNotFoundException(Exception):
    pass
