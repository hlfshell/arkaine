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

    @abstractmethod
    def completion(self, prompt: Prompt) -> str:
        pass
