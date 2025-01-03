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
        "claude-3-opus-20240229": 200_000,
        "claude-3-sonnet-20240229": 200_000,
        "claude-3-haiku-20240307": 200_000,
        "claude-2.1": 200_000,
        "claude-2.0": 100_000,
        "claude-instant-1.2": 100_000,
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
            # Map 'user' -> 'user' and 'assistant' -> 'assistant'
            # Map 'system' -> 'user' with a special prefix
            if msg["role"] == "system":
                messages.append(
                    {
                        "role": "user",
                        "content": f"\n\nHuman: {msg['content']}\n\nAssistant: "
                        + "I understand. I will follow these instructions.",
                    }
                )
            else:
                messages.append(msg)

        response = self.__client.messages.create(
            model=self.__model,
            messages=messages,
            temperature=self.default_temperature,
        )

        return response.content[0].text
