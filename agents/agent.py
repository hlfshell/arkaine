from abc import ABC, abstractmethod
from typing import Any, Callable, Dict, List, Optional

from agents.backends.base import BaseBackend
from agents.context import Context
from agents.llms.llm import LLM, Prompt
from agents.tools.tool import Argument, Example, Tool


class Agent(Tool, ABC):
    def __init__(
        self,
        name: str,
        description: str,
        args: List[Argument],
        llm: LLM,
        examples: List[Example] = [],
        process_answer: Optional[Callable[[str], Any]] = None,
    ):
        """
        An agent is a tool that utilizes an LLM. Prove an LLM model to generate
        completions, and implement prepare_prompt to convert incoming arguments
        to a prompt for your agent.

        The optional process_answer is a function that is fed the raw output of
        the LLM and converted in whatever manner you wish. If it is not
        provided, the raw output of the LLM is simply returned instead.
        """
        self.name = name
        self.description = description
        self.args = args
        self.examples = examples
        self.llm = llm
        self.process_answer = process_answer

    @abstractmethod
    def prepare_prompt(self, **kwargs) -> Prompt:
        """
        Given the arguments for the agent, create the prompt to feed to the LLM
        for execution.
        """
        pass

    def __call__(self, context: Optional[Context] = None, **kwargs):
        if context and not context.is_root:
            ctx = context.child_context()
        elif context and context.is_root:
            ctx = context
        else:
            ctx = None

        kwargs = self.fulfill_defaults(kwargs)

        try:
            self.check_arguments(kwargs)
            prompt = self.prepare_prompt(**kwargs)
            result = self.llm.completion(prompt)

            result = (
                self.process_answer(result) if self.process_answer else result
            )
            if ctx:
                ctx.output = result

            return result
        except Exception as e:
            if ctx:
                ctx.exception(e)
            raise e


class ToolAgent(Tool, ABC):

    def __init__(
        self,
        name: str,
        description: str,
        args: List[Argument],
        backend: BaseBackend,
        examples: List[Example] = [],
    ):
        self.name = name
        self.description = description
        self.args = args
        self.examples = examples
        self.backend = backend

    @abstractmethod
    def prepare_for_backend(self, **kwargs) -> Dict[str, Any]:
        """
        Given the arguments for the agent, transform them
        (if needed) for the backend's format. These will be
        passed to the backend as arguments.
        """
        pass

    def __call__(self, **kwargs) -> Any:
        kwargs = self.fulfill_defaults(kwargs)
        self.check_arguments(kwargs)
        args = self.prepare_for_backend(**kwargs)
        return self.backend.invoke(
            args=args, max_steps=5, stop_at_first_tool=True
        )
