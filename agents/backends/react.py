from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel

from agents.backends.base import BaseBackend
from agents.llms.llm import Prompt
from agents.tools.tool import ToolArguments, ToolResults


class ReActResponse(BaseModel):
    Thought: str
    Action: Optional[str] = None
    ActionInput: Optional[Dict[str, Any]] = None
    Answer: Optional[str] = None


class ReActBackend(BaseBackend):

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
            raise FormatException

        # Extract Action and Action Input
        while lines:
            line = lines.pop(0)
            if line.startswith("Action:"):
                results["Action"] = line.split("Action:", 1)[1].strip()
            elif line.startswith("Action Input:"):
                action_input_str = line.split("Action Input:", 1)[1].strip()
                try:
                    # Attempt to parse Action Input as JSON
                    results["Action Input"] = json.loads(action_input_str)
                except json.JSONDecodeError:
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
            raise ValueError("Action specified without Action Input")

        # Handle missing Answer if Action is present - necessary for
        # pydantic
        if results["Action"] is not None and results["Answer"] is None:
            results["Answer"] = ()

        # Convert Action Input to ActionInput for pydantic
        results["ActionInput"] = results["Action Input"]
        del results["Action Input"]

        # Use Pydantic for final validation and parsing
        return ReActResponse(**results)

    def parse_for_result(self, text: str) -> str:
        return self.__parse(text).Answer

    def parse_for_tool_calls(
        self, text: str, stop_at_first_tool: bool = False
    ) -> Dict[str, ToolArguments]:
        response = self.__parse(text)

        return {
            response.Action: response.ActionInput,
        }

    def tool_results_to_prompts(
        self, prompt: Prompt, results: ToolResults
    ) -> List[Prompt]:
        out = f"Observation:\nThe {results[0]} function returned the following information:\n"

        out += results[2]

        return prompt.append({"role": "system", "content": out})


class FormatException(Exception):
    pass


class ResponseException(Exception):
    pass


class ToolException(Exception):
    pass
