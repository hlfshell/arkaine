import os
from typing import Optional, Tuple, Union

from openai import OpenAI as OpenAIClient

from arkaine.llms.llm import LLM, Prompt


class DeepSeek(LLM):
    MODELS = {
        "deepseek-chat": {
            "context_length": 64000,
        },
        "deepseek-reasoner": {
            "context_length": 64000,
        },
    }

    def __init__(
        self,
        model: str = "deepseek-chat",
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        api_key: Optional[str] = None,
        context_length: Optional[int] = None,
    ):
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        api_key = api_key or os.getenv("DEEPSEEK_API_KEY")
        self.__client = OpenAIClient(
            api_key=api_key, base_url="https://api.deepseek.com/v1"
        )

        # Handle context_length
        if context_length is None:
            if self.model not in self.MODELS:
                raise ValueError(
                    f"Model {self.model} not found, context_length must be "
                    "provided"
                )
            self.__context_length = self.MODELS[self.model]["context_length"]
        else:
            self.__context_length = context_length

        self.__temperature = temperature

        self.__name = f"deepseek:{model}"

        super().__init__(name=self.__name)

    @property
    def context_length(self) -> int:
        return self.__context_length

    def completion(self, prompt: Prompt) -> Union[str, Tuple[str, str]]:
        params = {
            "model": self.model,
            "messages": prompt,
            "temperature": self.temperature,
        }

        if self.max_tokens is not None:
            params["max_tokens"] = self.max_tokens

        response = self.__client.chat.completions.create(**params)
        content = response.choices[0].message.content
        reasoning = ""
        try:
            reasoning = response.choices[0].message.model_extra[
                "reasoning_content"
            ]
        except:  # NOQA
            pass

        if not reasoning:
            return content
        else:
            return content, reasoning
