import os
from typing import Optional

import openai as oaiapi

from arkaine.llms.llm import LLM
from arkaine.tools.agent import Prompt


class OpenAI(LLM):

    MODELS = {
        "gpt-4o": {
            "context_length": 128000,
            "tokens_param": "max_completion_tokens",
            "supports_temperature": False,
        },
        "gpt-4o-mini": {
            "context_length": 128000,
            "tokens_param": "max_completion_tokens",
            "supports_temperature": False,
        },
        "o1": {
            "context_length": 200000,
            "tokens_param": "max_completion_tokens",
            "supports_temperature": False,
        },
        "o1-mini": {
            "context_length": 128000,
            "tokens_param": "max_completion_tokens",
            "supports_temperature": False,
        },
        "o1-preview": {
            "context_length": 128000,
            "tokens_param": "max_completion_tokens",
            "supports_temperature": False,
        },
        "o3-mini": {
            "context_length": 200000,
            "tokens_param": "max_completion_tokens",
            "supports_temperature": False,
        },
        "gpt-4-turbo": {
            "context_length": 128000,
            "tokens_param": "max_tokens",
            "supports_temperature": True,
        },
        "gpt-4-turbo-preview": {
            "context_length": 128000,
            "tokens_param": "max_tokens",
            "supports_temperature": True,
        },
        "gpt-4": {
            "context_length": 8192,
            "tokens_param": "max_tokens",
            "supports_temperature": True,
        },
        "gpt-3.5-turbo": {
            "context_length": 16385,
            "tokens_param": "max_tokens",
            "supports_temperature": True,
        },
    }

    def __init__(
        self,
        model: str = "gpt-3.5-turbo",
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        api_key: Optional[str] = None,
        context_length: Optional[int] = None,
        tokens_param: Optional[str] = None,
        supports_temperature: Optional[bool] = None,
    ):
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.__client = oaiapi.Client(api_key=api_key)

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

        # Handle tokens_param
        if tokens_param is None:
            if self.model not in self.MODELS and self.max_tokens is None:
                raise ValueError(
                    f"Model {self.model} not found, tokens_param must be "
                    "provided"
                )
            self.__tokens_param = self.MODELS[self.model]["tokens_param"]
        elif tokens_param not in ["max_tokens", "max_completion_tokens"]:
            raise ValueError(
                f"Invalid tokens_param: {tokens_param}, "
                "must be one of ['max_tokens', 'max_completion_tokens']"
            )
        else:
            self.__tokens_param = tokens_param

        # Handle supports_temperature
        if supports_temperature is None and self.model in self.MODELS:
            self.__supports_temperature = self.MODELS[self.model][
                "supports_temperature"
            ]
        else:
            self.__supports_temperature = supports_temperature or False

        self.__name = f"openai:{model}"

        super().__init__(name=self.__name)

    @property
    def context_length(self) -> int:
        return self.__context_length

    def completion(self, prompt: Prompt) -> str:
        params = {
            "model": self.model,
            "messages": prompt,
        }

        # Add temperature only if the model supports it
        if self.__supports_temperature:
            params["temperature"] = self.temperature

        # Use the appropriate tokens parameter based on the model
        if self.max_tokens is not None:
            params[self.__tokens_param] = self.max_tokens

        return (
            self.__client.chat.completions.create(**params)
            .choices[0]
            .message.content
        )
