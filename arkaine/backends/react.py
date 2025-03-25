from __future__ import annotations

import json
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

from arkaine.backends.backend import Backend, ToolNotFoundException
from arkaine.llms.llm import LLM, Prompt
from arkaine.tools.argument import InvalidArgumentException
from arkaine.tools.context import Context
from arkaine.tools.tool import Tool
from arkaine.tools.types import ToolArguments, ToolResults
from arkaine.utils.parser import Parser
from arkaine.utils.templater import PromptLoader


class ReActResponse:

    def __init__(
        self,
        thought: str,
        action: Optional[str] = None,
        action_input: Optional[Dict[str, Any]] = None,
        answer: Optional[str] = None,
    ):
        self.thought = thought
        self.action = action
        self.action_input = action_input
        self.answer = answer

    def __str__(self) -> str:
        out = f"Thought: {self.thought}\n"
        if self.action:
            out += f"Action: {self.action}\n"
            out += f"Action Input: {self.action_input}\n"
        if self.answer:
            out += f"Answer: {self.answer}\n"
        return out

    def __repr__(self) -> str:
        return self.__str__()

    def to_json(self) -> Dict[str, Any]:
        return {
            "thought": self.thought,
            "action": self.action,
            "action_input": self.action_input,
            "answer": self.answer,
        }

    @classmethod
    def from_json(cls, json_str: str) -> ReActResponse:
        return cls(**json.loads(json_str))


class ReActBackend(Backend):

    def __init__(
        self,
        llm: LLM,
        tools: List[Tool],
        agent_explanation: Optional[str] = None,
        initial_state: Dict[str, Any] = {},
        process_answer: Optional[Callable[[Any], Any]] = None,
        ignore_actions_without_input: bool = True,
    ):

        if initial_state is None:
            initial_state = {}
        initial_state["react_responses"] = []

        self.__parser = Parser(
            [
                "Thought",
                "Action",
                "Action Input",
                "Answer",
            ]
        )

        super().__init__(
            llm,
            tools,
            max_simultaneous_tools=1,
            initial_state=initial_state,
            process_answer=process_answer,
        )

        self.agent_explanation = agent_explanation
        self.__base_template = PromptLoader.load_prompt(
            "react_base",
        )
        self.__next_step_template = PromptLoader.load_prompt(
            "react_next_step",
        )
        self.ignore_actions_without_input = ignore_actions_without_input

    def __parse_old(self, context: Context, text: str) -> ReActResponse:
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
        context.append("react_responses", ReActResponse(**results))
        return ReActResponse(**results)

    def __parse(self, context: Context, text: str) -> ReActResponse:
        out = self.__parser.parse(text)
        context.append("react_responses", out)
        return out

    def parse_for_result(self, context: Context, text: str) -> Optional[str]:
        out = self.__parser.parse(text)
        if out.Answer:
            return out.Answer
        else:
            return None

    def parse_for_tool_calls(
        self, context: Context, text: str
    ) -> List[Tuple[str, ToolArguments]]:
        response = self.__parse(context, text)

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

    def format_tool_results(
        self, context: Context, results: ToolResults
    ) -> List[str]:
        out = ""
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

        return out

    @property
    def tool_names(self) -> str:
        if len(self.tools) > 1:
            return f"{', '.join(self.tools.keys())}"
        else:
            return f"The tool {list(self.tools.keys())[0]}"

    @property
    def tools_block(self) -> str:
        tools_block = ""
        for _, tool in self.tools.items():
            tools_block += f"{tool}\n"

        return tools_block

    def prepare_prompt(
        self, context: Context, tool_results: ToolResults, task: str
    ) -> Prompt:
        # Create the tool results block
        if context.get("prompt") is None:
            explanation = self.agent_explanation
            if explanation:
                explanation = f"{explanation}\n\n"
            else:
                explanation = (
                    "You are designed to help with a variety of tasks, "
                    "from answering questions to providing summaries to other "
                    "types of analyses."
                )
            return self.__base_template.render(
                {
                    "agent_explanation": explanation,
                    "tools_block": self.tools_block,
                    "tool_names": self.tool_names,
                    "task": task,
                }
            )
        else:
            tools_str = ""
            for tool_result in tool_results:
                tools_str += self.format_tool_results(context, tool_result)
                tools_str += "\n\n"

            last_response = context["react_responses"][-1]

            next_prompt = self.__next_step_template.render(
                {
                    "last_response": str(last_response),
                    "tools_results": tools_str,
                }
            )

            prompt = context["prompt"]
            prompt.append(next_prompt)
            return prompt


class FormatException(Exception):
    pass


class ResponseException(Exception):
    pass


class ToolException(Exception):
    pass
