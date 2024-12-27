from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional, Tuple

import openai as oaiapi
from openai.types.chat.chat_completion import ChatCompletion

from arkaine.agent import Prompt
from arkaine.backends.base import BaseBackend
from arkaine.backends.common import simple_tool_results_to_prompts
from arkaine.tools.tool import Context, Tool
from arkaine.tools.types import ToolArguments, ToolResults
from arkaine.utils.templater import PromptTemplate


class OpenAI(BaseBackend):

    def __init__(
        self,
        tools: List[Tool] = [],
        template: PromptTemplate = PromptTemplate.default(),
        max_simultaneous_tools: int = -1,
        api_key: Optional[str] = None,
        model: str = "gpt-3.5-turbo",
        temperature: float = 0.7,
        max_tokens: int = 1024,
        initial_state: Dict[str, Any] = {},
    ):
        super().__init__(None, tools, max_simultaneous_tools, initial_state)
        self.template = template
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.__client = oaiapi.Client(api_key=api_key)

    def parse_for_result(
        self, context: Context, response: ChatCompletion
    ) -> str:
        return response.choices[0].message.content

    def parse_for_tool_calls(
        self,
        context: Context,
        response: ChatCompletion,
        stop_at_first_tool: bool = False,
    ) -> List[Tuple[str, ToolArguments]]:
        """
        parse_for_tool_calls accepts a chatgpt response, extract all tool
        calls.

        Note that there is no "stop_at_first_tool" functionality on this
        function like other backends.
        """
        tool_calls: List[Dict[str, Any]] = []
        if response.choices[0].message.tool_calls:
            for tool_msg in response.choices[0].message.tool_calls:
                tool_name = tool_msg.function.name
                params = json.loads(tool_msg.function.arguments)

                tool_calls.append((tool_name, params))

        return tool_calls

    def tool_results_to_prompts(
        self,
        context: Context,
        prompt: Prompt,
        results: ToolResults,
    ) -> List[Prompt]:
        return simple_tool_results_to_prompts(prompt, results)

    def prepare_prompt(self, context: Context, **kwargs) -> Prompt:
        return self.template.render(kwargs)

    def query_model(self, prompt: Prompt) -> ChatCompletion:
        return self.__client.chat.completions.create(
            model=self.model,
            messages=prompt,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
            tools=[
                self.__tool_descriptor(tool) for tool in self.tools.values()
            ],
        )

    def __tool_descriptor(self, tool: Tool) -> Dict:
        properties = {}
        required_args = []

        for arg in tool.args:
            arg_type = arg.type_str()
            if arg_type == "str":
                arg_type = "string"

            properties[arg.name] = {
                "type": arg_type,
                "description": arg.description,
            }
            if arg.required:
                required_args.append(arg.name)

        return {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required_args,
                },
            },
        }
