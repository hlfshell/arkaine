import os
from typing import Optional

import google.generativeai as genai

from arkaine.llms.llm import LLM
from arkaine.tools.agent import Prompt


class Google(LLM):

    MODELS = {
        "gemini-pro": {"context_length": 30720},
        "gemini-1.0-pro": {"context_length": 30720},
        "gemini-2.0-flash-001": {"context_length": 1_000_000},
        "gemini-2.0-pro-exp-02-05": {"context_length": 2_000_000},
    }

    def __init__(
        self,
        model: str = "gemini-pro",
        api_key: Optional[str] = None,
        context_length: Optional[int] = None,
    ):
        if api_key is None:
            api_key = os.environ.get("GOOGLE_AISTUDIO_API_KEY")
            if api_key is None:
                api_key = os.environ.get("GOOGLE_API_KEY")
            if api_key is None:
                raise ValueError(
                    "No Google API key found. Please set "
                    "GOOGLE_AISTUDIO_API_KEY or GOOGLE_API_KEY "
                    "environment variable"
                )

        genai.configure(api_key=api_key)
        self.__model = genai.GenerativeModel(model_name=model)

        if context_length:
            self.__context_length = context_length
        elif model in Google.MODELS:
            self.__context_length = Google.MODELS[model]["context_length"]
        else:
            raise ValueError(
                f"Unknown model: {model} - must specify context length"
            )

        super().__init__(name=f"gemini:{model}")

    @property
    def context_length(self) -> int:
        return self.__context_length

    def completion(self, prompt: Prompt) -> str:
        # Convert the chat format to Gemini's expected format
        history = []
        for message in prompt:
            role = message["role"]
            content = message["content"]

            # Map OpenAI roles to Gemini roles
            if role == "system":
                history.append({"role": "user", "parts": [content]})
            elif role == "assistant":
                history.append({"role": "model", "parts": [content]})
            elif role == "user":
                history.append({"role": "user", "parts": [content]})

        # Create a chat session and send the entire history
        chat = self.__model.start_chat(history=history[:-1])
        response = chat.send_message(history[-1]["parts"][0])

        return response.text

    def __str__(self) -> str:
        return self.name
