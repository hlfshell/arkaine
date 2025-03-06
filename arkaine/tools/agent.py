from abc import ABC, abstractmethod
from typing import Any, Callable, Dict, List, Optional

from arkaine.backends.backend import Backend
from arkaine.llms.llm import LLM, Prompt
from arkaine.tools.result import Result
from arkaine.tools.tool import Argument, Context, Example, Tool


class Agent(Tool, ABC):
    """
    An agent is a tool that utilizes an LLM. Provide an LLM model to generate
    completions, and implement prepare_prompt to convert incoming arguments
    to a prompt for your agent.

    Args:
        name: The name of the agent.
        description: The description of the agent for other tools to use.
        args: The arguments of the agent.
        llm: The LLM model to use for the agent.
        examples: The examples of the agent to further explain its usage.
        result: The result of the agent.
        id: The id of the agent; generally leave this blank, as a UUID
            will be generated.
    """

    def __init__(
        self,
        name: str,
        description: str,
        args: List[Argument],
        llm: LLM,
        examples: List[Example] = [],
        result: Optional[Result] = None,
        id: Optional[str] = None,
    ):
        """
        An agent is a tool that utilizes an LLM. Prove an LLM model to generate
        completions, and implement prepare_prompt to convert incoming arguments
        to a prompt for your agent.

        The optional process_answer is a function that is fed the raw output of
        the LLM and converted in whatever manner you wish. If it is not
        provided, the raw output of the LLM is simply returned instead.
        """
        super().__init__(name, description, args, None, examples, id, result)
        self.llm = llm

    @abstractmethod
    def prepare_prompt(self, context: Context, **kwargs) -> Prompt:
        """
        Given the arguments for the agent, create the prompt to feed to the LLM
        for execution.
        """
        pass

    @abstractmethod
    def extract_result(self, context: Context, output: str) -> Optional[Any]:
        """
        Given the output of the LLM, extract the result.
        """
        pass

    def invoke(self, context: Context, **kwargs) -> Any:
        prompt = self.prepare_prompt(context, **kwargs)
        if isinstance(prompt, str):
            prompt = [{"role": "system", "content": prompt}]

        result = self.llm(context, prompt)

        final_result = self.extract_result(context, result)

        return final_result


class SimpleAgent(Agent):
    """
    SimpleAgent is a helper class that allows you to create an agent by
    providing a function to prepare the prompt and a function to extract the
    result, preventing the need to implement an inheriting agent.

    Args:
        name: The name of the agent.
        description: The description of the agent for other tools to use.
        args: The arguments of the agent.
        llm: The LLM model to use for the agent.
        prepare_prompt: A function to prepare the prompt for the agent.
        extract_result: A function to extract the result from the LLM.
        examples: The examples of the agent to further explain its usage.
        id: The id of the agent; generally leave this blank, as a UUID
            will be generated.
        result: The result of the agent; optional.
    """

    def __init__(
        self,
        name: str,
        description: str,
        args: List[Argument],
        llm: LLM,
        prepare_prompt: Callable[[Context, Any], Prompt],
        extract_result: Optional[Callable[[Context, str], Optional[Any]]],
        examples: List[Example] = [],
        id: Optional[str] = None,
        result: Optional[Result] = None,
    ):
        super().__init__(name, description, args, llm, examples, id, result)

        self.__prompt_function = prepare_prompt
        self.__extract_result_function = extract_result

    def prepare_prompt(self, context: Context, **kwargs) -> Prompt:
        return self.__prompt_function(context, **kwargs)

    def extract_result(self, context: Context, output: str) -> Optional[Any]:
        if self.__extract_result_function:
            return self.__extract_result_function(context, output)
        return output


class IterativeAgent(Agent):
    """
    IterativeAgent is an agent that can iterate on a task until a result is
    found. It will continue to call the LLM with the provided prompt until the
    result is not None.

    Args:
        name: The name of the agent.
        description: The description of the agent for other tools to use.
        args: The arguments of the agent.
        llm: The LLM model to use for the agent.
        examples: The examples of the agent to further explain its usage.
        result: The result of the agent; optional.
        initial_state: The initial state of the agent.
        max_steps: The maximum number of steps the agent can take.
        id: The id of the agent; generally leave this blank, as a UUID
            will be generated.
    """

    def __init__(
        self,
        name: str,
        description: str,
        args: List[Argument],
        llm: LLM,
        examples: List[Example] = [],
        result: Optional[Result] = None,
        initial_state: Dict[str, Any] = {},
        max_steps: Optional[int] = None,
        id: Optional[str] = None,
    ):
        super().__init__(name, description, args, llm, examples, id, result)
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
            output = self.llm(context, prompt)

            result = self.extract_result(context, output)
            if result is not None:
                return result


class SimpleIterativeAgent(IterativeAgent):
    """
    SimpleIterativeAgent is a helper class that allows you to create an
    iterative agent by providing a function to prepare the prompt and a
    function to extract the result, preventing the need to implement an
    inheriting agent.

    Args:
        name: The name of the agent.
        description: The description of the agent for other tools to use.
        args: The arguments of the agent.
        llm: The LLM model to use for the agent.
        prepare_prompt: A function to prepare the prompt for the agent.
        extract_result: A function to extract the result from the LLM.
        examples: The examples of the agent to further explain its usage.
        id: The id of the agent; generally leave this blank, as a UUID
            will be generated.
        result: The result of the agent; optional.
    """

    def __init__(
        self,
        name: str,
        description: str,
        args: List[Argument],
        llm: LLM,
        prepare_prompt: Callable[[Context, Any], Prompt],
        extract_result: Optional[Callable[[Context, str], Optional[Any]]],
        initial_state: Dict[str, Any] = {},
        max_steps: Optional[int] = None,
        examples: List[Example] = [],
        id: Optional[str] = None,
        result: Optional[Result] = None,
    ):
        super().__init__(
            name,
            description,
            args,
            llm,
            examples,
            result,
            initial_state,
            max_steps,
            id,
        )
        self.__prepare_prompt = prepare_prompt
        self.__extract_result = extract_result

    def prepare_prompt(self, context: Context, **kwargs) -> Prompt:
        return self.__prepare_prompt(context, **kwargs)

    def extract_result(self, context: Context, output: str) -> Optional[Any]:
        return self.__extract_result(context, output)


class BackendAgent(Tool):
    """
    BackendAgent is an agent that utilizes a backend to execute the agent's
    task. It will prepare the arguments for the backend and then invoke the
    backend with the prepared arguments.

    Args:
        name: The name of the agent.
        description: The description of the agent for other tools to use.
        agent_explanation: The explanation of the agent to explain to the
            LLM what the goal of the agent is.
        args: The arguments of the agent.
        backend: The backend to use for the agent.
        examples: The examples of the agent to further explain its usage.
        id: The id of the agent; generally leave this blank, as a UUID
            will be generated.
        result: The result of the agent; optional.
    """

    def __init__(
        self,
        name: str,
        description: str,
        agent_explanation: str,
        args: List[Argument],
        backend: Backend,
        examples: List[Example] = [],
        result: Optional[Result] = None,
        id: Optional[str] = None,
    ):
        super().__init__(name, description, args, None, examples, id, result)
        self.backend = backend
        self.agent_explanation = agent_explanation

    def prepare_for_backend(
        self,
        context: Context,
        **kwargs,
    ) -> Dict[str, Any]:
        """
        Given the arguments for the agent, transform them
        (if needed) for the backend's format. These will be
        passed to the backend as arguments. By default,
        the backend agent will pass the arguments as-is to the
        backend; overwrite this method in your implementation
        if need be.

        Typically, you want to convert all arguments into:

        {
            "task": "...",
        }

        ...wherein the task is a string that describes the current
        task clearly to the agent given its explanation.
        """
        return kwargs

    def invoke(self, context: Context, **kwargs) -> Any:
        prepared_args = self.prepare_for_backend(context, **kwargs)
        return self.backend.invoke(context, prepared_args)
