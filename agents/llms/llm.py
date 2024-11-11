from abc import ABC, abstractmethod
from typing import Dict, List

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

    @abstractmethod
    def completion(self, prompt: Prompt) -> str:
        """
        completion takes a prompt and queries the model to generate a
        completion. The string body of the completion is returned.
        """
        pass
