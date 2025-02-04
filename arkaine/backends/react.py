from __future__ import annotations

import json
import pathlib
from os import path
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

from pydantic import BaseModel

from arkaine.backends.backend import Backend, ToolNotFoundException
from arkaine.llms.llm import LLM, Prompt
from arkaine.tools.argument import InvalidArgumentException
from arkaine.tools.context import Context
from arkaine.tools.tool import Tool
from arkaine.tools.types import ToolArguments, ToolResults
from arkaine.utils.templater import PromptTemplate


class ReActResponse(BaseModel):
    Thought: str
    Action: Optional[str] = None
    ActionInput: Optional[Dict[str, Any]] = None
    Answer: Optional[str] = None


class ReActBackend(Backend):

    def __init__(
        self,
        llm: LLM,
        tools: List[Tool],
        agent_explanation: str,
        initial_state: Dict[str, Any] = {},
        process_answer: Optional[Callable[[Any], Any]] = None,
        ignore_actions_without_input: bool = True,
    ):
        super().__init__(
            llm,
            tools,
            max_simultaneous_tools=1,
            initial_state=initial_state,
            process_answer=process_answer,
        )

        self.agent_explanation = agent_explanation
        self.__templater = PromptTemplate.from_file(
            path.join(
                pathlib.Path(__file__).parent,
                "prompts",
                "react.prompt",
            )
        )
        self.ignore_actions_without_input = ignore_actions_without_input

    def __parse(self, text: str) -> ReActResponse:
        lines = text.strip().split("\n")
        results: Dict[str, Optional[Union[str, Dict]]] = {
            "Thought": None,
            "Action": None,
            "Action Input": None,
            "Answer": None,
        }

        # Extract Thought
        if lines and lines[0].startswith("Thought:"):
            results["Thought"] = lines.pop(0).split("Thought:", 1)[1].strip()
        else:
            # raise FormatException
            results["Thought"] = ""

        # Extract Action and Action Input
        while lines:
            line = lines.pop(0)
            if not line.strip():
                continue
            if line.startswith("Action:"):
                results["Action"] = line.split("Action:", 1)[1].strip()
            elif line.startswith("Action Input:"):
                action_input_str = line.split("Action Input:", 1)[1].strip()
                try:
                    # First try to parse as JSON
                    results["Action Input"] = json.loads(action_input_str)
                except json.JSONDecodeError:
                    try:
                        # If JSON fails, try evaluating as Python literal
                        # Replace None, True, False with their JSON equivalents
                        action_input_str = (
                            action_input_str.replace("None", "null")
                            .replace("True", "true")
                            .replace("False", "false")
                        )
                        results["Action Input"] = json.loads(action_input_str)
                    except json.JSONDecodeError:
                        # If both fail, use the raw string
                        results["Action Input"] = action_input_str
            elif line.startswith("Answer:"):
                # Found the answer, capture it and any remaining lines
                results["Answer"] = (
                    line.split("Answer:", 1)[1].strip()
                    + "\n"
                    + "\n".join(lines)
                )
                break  # Stop processing after finding the answer

        # Validation
        if results["Action"] is not None and results["Action Input"] is None:
            if not self.ignore_actions_without_input:
                raise ValueError("Action specified without Action Input")
            else:
                results["Action"] = None
                results["Action Input"] = None

        # Handle missing Answer if Action is present - necessary for
        # pydantic
        if results["Action"] is not None and results["Answer"] is None:
            results["Answer"] = ""

        # Convert Action Input to ActionInput for pydantic
        results["ActionInput"] = results["Action Input"]
        del results["Action Input"]

        # If everything is blank, usually the model has output
        # the answer without the thought or Answer label
        if (
            not results["Thought"]
            and not results["Action"]
            and not results["ActionInput"]
            and not results["Answer"]
        ):
            results["Answer"] = text.strip()

        # Use Pydantic for final validation and parsing
        return ReActResponse(**results)

    def parse_for_result(self, context: Context, text: str) -> str:
        return self.__parse(text).Answer

    def parse_for_tool_calls(
        self, context: Context, text: str, stop_at_first_tool: bool = False
    ) -> List[Tuple[str, ToolArguments]]:
        response = self.__parse(text)

        return (
            []
            if not response.Action
            else [
                (
                    response.Action,
                    response.ActionInput,
                )
            ]
        )

    def tool_results_to_prompts(
        self, context: Context, prompt: Prompt, results: ToolResults
    ) -> List[Prompt]:
        for name, args, result in results:
            out = f"---\n{name}("

            first_tool = True
            for arg, value in args.items():
                if first_tool:
                    first_tool = False
                else:
                    out += ", "
                out += f"{arg}="
                if isinstance(value, str):
                    out += f'"{value}"'
                else:
                    out += f"{value}"
            out += ") "

            if isinstance(result, InvalidArgumentException):
                out += "encountered an error with the arguments passed"
                out += f"for this tool:\n{result}\n"
                out += "Remember the tool expects the following arguments:\n"
                out += (
                    "\n".join(str(arg) for arg in self.tools[name].args) + "\n"
                )
            elif isinstance(result, ToolNotFoundException):
                out += "\nNo such tool exists.\n"
                out += "Remember you have access to the following tools: "
                out += f"{','.join(self.tools.keys())}\n"
            else:
                out += f"returned:\n{result}\n"

            prompt.append(
                {
                    "role": "system",
                    "content": out,
                }
            )
        return prompt

    def prepare_prompt(self, context: Context, **kwargs) -> Prompt:
        # Create the tools block
        tools_block = ""
        for _, tool in self.tools.items():
            tools_block += f"{tool}\n"

        if len(self.tools) > 1:
            tool_names = f"{', '.join(self.tools.keys())}"
        else:
            tool_names = f"The tool {list(self.tools.keys())[0]}"

        return self.__templater.render(
            {
                # "agent_explanation": self.agent_explanation,
                "tools_block": tools_block,
                "tool_names": tool_names,
                "task": kwargs["task"],
            }
        )


class FormatException(Exception):
    pass


class ResponseException(Exception):
    pass


class ToolException(Exception):
    pass
