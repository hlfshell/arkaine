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
        context_length: int = 8192,
    ):
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.__client = oaiapi.Client(api_key=api_key)
        self.__context_length = context_length

    @property
    def context_length(self) -> int:
        return self.__context_length

    def completion(self, prompt: Prompt) -> str:
        return (
            self.__client.chat.completions.create(
                model=self.model,
                messages=prompt,
                max_tokens=self.max_tokens,
                temperature=self.temperature,
            )
            .choices[0]
            .message.content
        )
