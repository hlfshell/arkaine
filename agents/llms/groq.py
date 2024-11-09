import os
from typing import Optional

from groq import Groq

from agents.agent import Prompt
from agents.llms.llm import LLM


class GroqLLM(LLM):

    def __init__(
        self, model: str = "llama3-70b-8192", api_key: Optional[str] = None
    ):
        if api_key is None:
            api_key = os.environ.get("GROQ_API_KEY")
        self.__client = Groq(api_key=api_key)
        self.__model = model

    def completion(self, prompt: Prompt) -> str:
        if isinstance(prompt, str):
            prompt = [
                {
                    "role": "system",
                    "content": prompt,
                }
            ]

        response = self.__client.chat.completions.create(
            model=self.__model,
            messages=prompt,
        )

        return response.choices[0].message.content
