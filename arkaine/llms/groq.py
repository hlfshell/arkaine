import os
from typing import Optional

from groq import Groq as GroqAPI

from arkaine.agent import Prompt
from arkaine.llms.llm import LLM


class Groq(LLM):

    CONTEXT_LENGTHS = {
        "gemma2-9b-it": 8192,
        "gemma-7b-it": 8192,
        "llama-3.3-70b-versatile": 32768,
        "llama-3.1-70b-versatile": 32768,
        "llama-3.1-8b-instant": 8192,
        "llama-guard-3-8b": 8192,
        "llama3-70b-8192": 8192,
        "llama3-8b-8192": 8192,
        "mixtral-8x7b-32768": 32768,
        "llama3-groq-70b-8192-tool-use-preview": 8192,
        "llama3-groq-8b-8192-tool-use-preview": 8192,
        "llama-3.3-70b-specdec": 8192,
        "llama-3.1-70b-specdec": 8192,
        "llama-3.3-70b-vision-preview": 128768,
        "llama-3.1-70b-vision-preview": 128768,
        "llama-3.2-1b-preview": 1288192,
        "llama-3.2-3b-preview": 1288192,
        "llama-3.2-11b-vision-preview": 1288192,
        "llama-3.2-90b-vision-preview": 128768,
    }

    def __init__(
        self,
        model: str = "llama3-70b-8192",
        api_key: Optional[str] = None,
        context_length: Optional[int] = 8192,
    ):
        if api_key is None:
            api_key = os.environ.get("GROQ_API_KEY")
        self.__client = GroqAPI(api_key=api_key)
        self.__model = model
        if context_length:
            self.__context_length = context_length
        elif model in self.CONTEXT_LENGTHS:
            self.__context_length = self.CONTEXT_LENGTHS[model]
        else:
            raise ValueError(
                f"Unknown model: {model} - must specify context length"
            )

        super().__init__(name=f"groq:{model}")

    @property
    def context_length(self) -> int:
        return self.__context_length

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

    def __str__(self) -> str:
        return self.name
