import os
from typing import Optional

from groq import Groq as GroqAPI

from arkaine.llms.llm import LLM
from arkaine.tools.agent import Prompt


class Groq(LLM):

    MODELS = {
        "gemma2-9b-it": {"context_length": 8192},
        "llama-3.3-70b-versatile": {"context_length": 128000},
        "llama-3.1-8b-instant": {"context_length": 8192},
        "llama-guard-3-8b": {"context_length": 8192},
        "llama3-70b-8192": {"context_length": 8192},
        "llama3-8b-8192": {"context_length": 8192},
        "mixtral-8x7b-32768": {"context_length": 32768},
        "llama-3.2-1b-preview": {"context_length": 128000},
        "llama-3.2-3b-preview": {"context_length": 128000},
        "llama-3.2-11b-vision-preview": {"context_length": 128000},
        "llama-3.2-90b-vision-preview": {"context_length": 128000},
        "deepseek-r1-distill-llama-70b": {"context_length": 128000},
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
        elif model in self.MODELS:
            self.__context_length = self.MODELS[model]["context_length"]
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
