from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional, Tuple, Union

import openai as oaiapi
from openai.types.chat.chat_completion import ChatCompletion

from agents.backends.base import BaseBackend
from agents.backends.common import simple_tool_results_to_prompts

# from agents.llms.openai import OpenAILLM
from agents.templater import PromptTemplate
from agents.tools.tool import Tool, ToolArguments


class OpenAI(BaseBackend):

    def __init__(
        self,
        tools: List[Tool],
        template: PromptTemplate,
        max_simultaneous_tools: int = 1,
        api_key: Optional[str] = None,
        model: str = "gpt-3.5-turbo",
        temperature: float = 0.7,
        max_tokens: int = 1024,
    ):
        super().__init__(None, tools, max_simultaneous_tools)
        self.template = template

        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.__client = oaiapi.Client(api_key=api_key)

    def __tool_descriptor(self, tool: Tool) -> Dict:
        properties = {}
        required_args = []

        for arg in tool.args:
            properties[arg.name] = {
                "type": arg.type,
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

    def parse_for_result(self, response: ChatCompletion) -> str:
        return response.choices[0].message.content

    def parse_for_tool_calls(
        self, text: str, stop_at_first_tool: bool = False
    ) -> List[Tuple[str, ToolArguments]]:
        raise NotImplementedError

    def tool_results_to_prompts(
        self,
        prompt: List[Dict[str, str]],
        results: List[Tuple[str | Dict[str, Any] | Any]],
    ) -> List[List[Dict[str, str]]]:
        return simple_tool_results_to_prompts(prompt, results)

    def prepare_prompt(self, **kwargs) -> List[Dict[str, str]]:
        return self.template.render(kwargs)

    def invoke(
        self,
        args: Dict[str, Any],
        max_steps: Optional[int] = None,
        stop_at_first_tool: bool = False,
    ):
        steps = 0

        prompt = self.prepare_prompt(**args)

        tools = [self.__tool_descriptor(tool) for _, tool in self.tools.items()]

        while True:
            steps += 1
            if max_steps and steps > max_steps:
                raise Exception("too many steps")

            response = self.__client.chat.completions.create(
                model=self.model,
                messages=prompt,
                temperature=self.temperature,
                tools=tools,
            )

            tool_calls: List[str, Dict[str, Any]] = []
            if response.choices[0].message.tool_calls:
                for tool_msg in response.choices[0].message.tool_calls:
                    tool_name = tool_msg.function.name
                    params = json.loads(tool_msg.function.arguments)

                    tool_calls.append((tool_name, params))

            if len(tool_calls) > 0:
                tool_results = self.call_tools(tool_calls)
                prompt = self.tool_results_to_prompts(prompt, tool_results)
            else:
                return self.parse_for_result(response)
