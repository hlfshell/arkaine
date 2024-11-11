import os
from typing import Dict, List, Optional

import openai as oaiapi
from openai.types.chat.chat_completion import ChatCompletion

from agents.agent import Prompt
from agents.llms.llm import LLM
from agents.tools.tool import Tool


class OpenAI(LLM):

    def __init__(
        self,
        model: str,
        temperature: float = 0.7,
        max_tokens: int = 1024,
        api_key: Optional[str] = None,
    ):
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

    def completion(self, prompt: Prompt, tools: List[Tool]) -> ChatCompletion:
        return self.__client.chat.completions.create(
            model=self.model,
            messages=prompt,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
            tools=[self.__tool_descriptor(tool) for tool in tools],
        )
