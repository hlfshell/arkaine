import re
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Union

from arkaine.tools.events import Event
from arkaine.tools.tool import Context

# A RolePrompt is a dict specifying a role, and a string specifying the
# content. An example of this would be:
# { "role": "system", "content": "You are a an assistant AI whom should answer
# all questions in a straightforward manner" }
# { "role": "user", "content": "How much wood could a woodchuck chuck..." }
RolePrompt = Dict[str, str]

# Prompt is a union type - either a straight string, or a RolePrompt.
Prompt = List[RolePrompt]


class LLM(ABC):

    def __init__(
        self,
        name: str = None,
    ):
        super().__init__()
        self.name = name

    @property
    @abstractmethod
    def context_length(self) -> int:
        """
        context_length returns the maximum length of context the model can
        accept.
        """
        pass

    def estimate_tokens(
        self, content: Union[Prompt, List[Prompt], List[str], str]
    ) -> int:
        """
        estimate_tokens estimates the number of tokens in the prompt, as best
        as possible, since many models do not share their tokenizers. Unless
        overwritten by a subclass, this will estimate tokens via the following
        rules:

        1. All spaces, new lines, punctuation, and special characters are
           counted as 1 token.
        2. We count the number of words and multiply by 1.33 (0.75 words per
           token average) AND take the number of remaining characters after 1
           and divide by 4 (3 characters per token average). We return the
           smaller of these two added with 1.

        Prompts are considered for their content only, not their role or the
        potential tokenization of their formatting symbols.
        """
        # Convert the content to a list of strings for counting.
        if isinstance(content, Prompt):
            content = [content]
        elif isinstance(content, List[Prompt]):
            content = [item for sublist in content for item in sublist]
        elif isinstance(content, List[str]):
            pass
        elif isinstance(content, str):
            content = [content]
        else:
            raise ValueError(f"Unknown content type: {type(content)}")

        # For each string in our list of strings, count and add it up
        count = 0
        for string in content:
            # Remove all punctuation, spaces, new lines, and other formatting
            removed = re.sub(r"[^\w\s]", "", string)
            count += len(removed)

            # Determine which is smaller - isolated words or characters / 4
            chars_count = len(string) - len(removed) / 4

            # Create a list of words, trimming new lines and standalone
            # characters
            words = re.split(r"\s+", string)
            words_count = len(words) * 1.33

            count += min(chars_count, words_count)

        return count

    @abstractmethod
    def completion(self, prompt: Prompt) -> str:
        """
        completion takes a prompt and queries the model to generate a
        completion. The string body of the completion is returned.
        """
        pass

    def extract_arguments(self, args, kwargs):
        # Extract context if present as first argument
        context = None
        if args and isinstance(args[0], Context):
            context = args[0]
            args = args[1:]

        if len(args) == 1 and not kwargs and isinstance(args[0], dict):
            kwargs = args[0]
            args = ()

        # Extract prompt from args or kwargs
        prompt = None
        if len(args) == 1:
            prompt = args[0]
        elif "prompt" in kwargs:
            prompt = kwargs.pop("prompt")
        else:
            raise TypeError("prompt argument is required")

        # Check to see if context is in the kwargs
        if "context" in kwargs:
            if context is not None:
                raise ValueError("context passed twice")
            context = kwargs.pop("context")

        if kwargs:
            raise TypeError(
                f"Unexpected keyword arguments: {', '.join(kwargs.keys())}"
            )

        if isinstance(prompt, str):
            prompt = [{"role": "user", "content": prompt}]

        return context, prompt

    def _init_context_(
        self, context: Optional[Context], prompt: Prompt
    ) -> Context:
        if context is None:
            ctx = Context(self)
        else:
            ctx = context

        if ctx.executing:
            ctx = context.child_context(self)
            ctx.executing = True
        else:
            if not ctx.tool:
                ctx.tool = self
            ctx.executing = True

        ctx.args = prompt

    def __call__(self, *args, **kwargs) -> str:
        context, prompt = self.extract_arguments(args, kwargs)

        with self._init_context_(context, prompt) as ctx:
            ctx.broadcast(LLMCalled(prompt))
            response = self.completion(prompt)
            ctx.broadcast(LLMResponse(response))
            return response


class LLMCalled(Event):

    def __init__(self, prompt: Union[Prompt, str]):
        super().__init__("llm_called", prompt)

    def __str__(self) -> str:
        if isinstance(self.data, str):
            return f"{self._get_readable_timestamp()}:\n{self.data}"
        else:
            out = f"{self._get_readable_timestamp()}:\n"
            for role, content in self.data:
                out += f"{role}:\n{content}\n"
                out += "---\n"
            return out


class LLMResponse(Event):

    def __init__(self, response: str):
        super().__init__("llm_response", response)

    def __str__(self) -> str:
        return f"{self._get_readable_timestamp()}:\n{self.data}"
