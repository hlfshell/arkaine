import re
from abc import ABC, abstractmethod
from typing import Dict, List, Union

# A RolePrompt is a dict specifying a role, and a string specifying the
# content. An example of this would be:
# { "role": "system", "content": "You are a an assistant AI whom should answer
# all questions in a straightforward manner" }
# { "role": "user", "content": "How much wood could a woodchuck chuck..." }
RolePrompt = Dict[str, str]

# Prompt is a union type - either a straight string, or a RolePrompt.
# Prompt = Union[str, List[RolePrompt]]


Prompt = List[RolePrompt]


class LLM(ABC):

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
