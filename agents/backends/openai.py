from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional, Tuple, Union

from openai.types.chat.chat_completion import ChatCompletion

from agents.agent import Prompt
from agents.backends.base import BaseBackend
from agents.backends.common import simple_tool_results_to_prompts
from agents.llms.llm import LLM
from agents.llms.openai import OpenAI as OpenAILLM
from agents.templater import PromptTemplate
from agents.tools.tool import Tool, ToolArguments, ToolResults


class OpenAI(BaseBackend):

    def __init__(
        self,
        tools: List[Tool],
        template: PromptTemplate,
        max_simultaneous_tools: int = -1,
        api_key: Optional[str] = None,
        model: str = "gpt-3.5-turbo",
        temperature: float = 0.7,
        max_tokens: int = 1024,
    ):
        llm = OpenAILLM(model, temperature, max_tokens, api_key)
        super().__init__(llm, tools, max_simultaneous_tools)
        self.template = template

    def parse_for_result(self, response: ChatCompletion) -> str:
        return response.choices[0].message.content

    def parse_for_tool_calls(
        self, response: ChatCompletion, stop_at_first_tool: bool = False
    ) -> ToolResults:
        """
        parse_for_tool_calls accepts a chatgpt response, extract all tool
        calls.

        Note that there is no "stop_at_first_tool" functionality on this
        function like other backends.
        """
        tool_calls: List[str, Dict[str, Any]] = []
        if response.choices[0].message.tool_calls:
            for tool_msg in response.choices[0].message.tool_calls:
                tool_name = tool_msg.function.name
                params = json.loads(tool_msg.function.arguments)

                tool_calls.append((tool_name, params))

        return tool_calls

    def tool_results_to_prompts(
        self,
        prompt: Prompt,
        results: ToolResults,
    ) -> List[List[Dict[str, str]]]:
        return simple_tool_results_to_prompts(prompt, results)

    def prepare_prompt(self, **kwargs) -> Prompt:
        return self.template.render(kwargs)
