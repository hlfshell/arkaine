import os
from typing import Optional

import openai as oaiapi

from arkaine.agent import Prompt
from arkaine.llms.llm import LLM


class OpenAI(LLM):

    CONTEXT_LENGTHS = {
        "gpt-4o": 128000,
        "gpt-4o-mini": 8192,
        "gpt-3.5-turbo": 4096,
        "gpt-4": 8192,
        "gpt-4-32k": 32768,
        "gpt-3": 2048,
        "text-davinci-003": 4096,
        "code-davinci-002": 8001,
        "o1": 128000,
        "o1-mini": 8192,
        "gpt-4-turbo-preview": 128000,
        "gpt-4-1106-preview": 128000,
        "gpt-4-0125-preview": 128000,
        "gpt-4-0613": 8192,
        "gpt-4-0314": 8192,
    }

    def __init__(
        self,
        model: str = "gpt-3.5-turbo",
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

        self.__name = f"openai:{model}"

        super().__init__(name=self.__name)

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
