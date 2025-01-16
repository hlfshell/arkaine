from abc import ABC, abstractmethod
from typing import Any, Callable, Dict, List, Optional

from arkaine.backends.base import BaseBackend
from arkaine.events import AgentLLMCalled, AgentLLMResponse, AgentPrompt
from arkaine.llms.llm import LLM, Prompt
from arkaine.tools.tool import Argument, Context, Example, Tool


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
        super().__init__(name, description, args, None, examples)
        self.llm = llm
        self.process_answer = process_answer

    @abstractmethod
    def prepare_prompt(self, **kwargs) -> Prompt:
        """
        Given the arguments for the agent, create the prompt to feed to the LLM
        for execution.
        """
        pass

    def invoke(self, context: Context, **kwargs) -> Any:
        prompt = self.prepare_prompt(**kwargs)
        if isinstance(prompt, str):
            prompt = [{"role": "system", "content": prompt}]

        context.broadcast(AgentPrompt(prompt))
        context.broadcast(AgentLLMCalled())
        result = self.llm.completion(prompt)
        context.broadcast(AgentLLMResponse(result))

        final_result = (
            self.process_answer(result) if self.process_answer else result
        )

        return final_result


class IterativeAgent(Agent):

    def __init__(
        self,
        name: str,
        description: str,
        args: List[Argument],
        llm: LLM,
        examples: List[Example] = [],
        initial_state: Dict[str, Any] = {},
        max_steps: Optional[int] = None,
    ):
        super().__init__(name, description, args, llm, examples)
        self.__initial_state = initial_state
        self.max_steps = max_steps

    @abstractmethod
    def prepare_prompt(self, context: Context, **kwargs) -> Prompt:
        pass

    @abstractmethod
    def extract_result(self, context: Context, output: str) -> Optional[Any]:
        pass

    def __initialize_state(self, context: Context):
        if self.__initial_state:
            state = self.__initial_state.copy()
            for arg in state:
                context[arg] = state[arg]

    def invoke(self, context: Context, **kwargs) -> Any:
        self.__initialize_state(context)
        step = 0

        while True:
            step += 1
            if self.max_steps and step > self.max_steps:
                raise Exception("Max steps reached")

            prompt = self.prepare_prompt(context, **kwargs)
            context.broadcast(AgentPrompt(prompt))
            context.broadcast(AgentLLMCalled())
            result = self.llm.completion(prompt)
            context.broadcast(AgentLLMResponse(result))

            result = self.extract_result(context, result)
            if result is not None:
                return result


class BackendAgent(Tool, ABC):

    def __init__(
        self,
        name: str,
        description: str,
        args: List[Argument],
        backend: BaseBackend,
        examples: List[Example] = [],
    ):
        super().__init__(name, description, args, None, examples)
        self.backend = backend

    @abstractmethod
    def prepare_for_backend(self, **kwargs) -> Dict[str, Any]:
        """
        Given the arguments for the agent, transform them
        (if needed) for the backend's format. These will be
        passed to the backend as arguments.
        """
        pass

    def invoke(self, context: Context, **kwargs) -> Any:
        return self.backend.invoke(context, self.prepare_for_backend(**kwargs))
