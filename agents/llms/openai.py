import os
from typing import Optional

import openai

from agents.agent import Prompt
from agents.llms.llm import LLM


class GPT(LLM):
    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "gpt-3.5-turbo",
        temperature: float = 0.7,
        max_tokens: int = 1024,
    ):
        self.model = model

        self.__api_key = api_key or os.getenv("OPENAI_API_KEY")

        self.client = openai.Client(api_key=self.__api_key)

        self.temperature = temperature
        self.max_tokens = max_tokens

    def completion(self, prompt: Prompt) -> str:
        response = self.client.chat.completions.create(
            model=self.model,
            messages=prompt,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
        )

        return response.choices[0].message.content
