import os
from typing import Optional

from anthropic import Anthropic

from arkaine.agent import Prompt
from arkaine.llms.llm import LLM


class Claude(LLM):
    """
    Claude implements the LLM interface for Anthropic's Claude models.
    """

    CONTEXT_LENGTHS = {
        "claude-3-opus-20240229": 4096,
        "claude-3-sonnet-20240229": 4096,
        "claude-3-haiku-20240307": 4096,
        "claude-2.1": 4096,
        "claude-2.0": 4096,
        "claude-instant-1.2": 4096,
    }

    def __init__(
        self,
        model: str = "claude-3-sonnet-20240229",
        api_key: Optional[str] = None,
        context_length: Optional[int] = None,
        default_temperature: float = 0.7,
    ):
        """
        Initialize a new Claude LLM instance.

        Args:
            model: The Claude model to use
            api_key: Anthropic API key. If None, will look for
                ANTHROPIC_API_KEY env var
            context_length: Optional override for model's context
                length
            default_temperature: Default temperature for completions (0.0-1.0)
        """
        if api_key is None:
            api_key = os.environ.get("ANTHROPIC_API_KEY")
            if api_key is None:
                raise ValueError(
                    "No API key provided and ANTHROPIC_API_KEY environment "
                    + " variable not set"
                )

        self.__client = Anthropic(api_key=api_key)
        self.__model = model
        self.default_temperature = default_temperature

        if context_length:
            self.__context_length = context_length
        elif model in self.CONTEXT_LENGTHS:
            self.__context_length = self.CONTEXT_LENGTHS[model]
        else:
            raise ValueError(f"Unknown model: {model}")

        super().__init__(name=f"claude:{model}")

    @property
    def context_length(self) -> int:
        return self.__context_length

    def completion(self, prompt: Prompt) -> str:
        """
        Generate a completion from Claude given a prompt.

        Args:
            prompt: List of message dictionaries with 'role' and 'content' keys

        Returns:
            The generated completion text
        """
        # Convert the messages format if needed
        messages = []
        for msg in prompt:
            if msg["role"] == "system":
                messages.append({"role": "user", "content": msg["content"]})
            else:
                messages.append(msg)

        messages.append(
            {
                "role": "assistant",
                "content": "I understand. I will follow these instructions.",
            }
        )

        attempts = 0
        while True:
            attempts += 1
            if attempts > 3:
                raise Exception("Failed to get a response from Claude")
            response = self.__client.messages.create(
                model=self.__model,
                messages=messages,
                temperature=self.default_temperature,
                max_tokens=self.context_length,
            )
            if response.content:
                break

        return response.content[0].text
