from typing import Any, Callable, Dict, List, Optional, Union

from arkaine.tools.events import ToolReturn
from arkaine.tools.tool import Argument, Context, Example, Tool
from arkaine.tools.toolify import toolify


class DoWhile(Tool):
    """
    A tool that executes a sequence of steps repeatedly while a condition is met.
    The condition is evaluated after each iteration, ensuring the steps are executed
    at least once.

    Args:
        tool (Tool): The tool to repeatedly trigger

        condition (Callable[[Context, Any], bool]): Function that evaluates whether
            to continue the loop. Takes the context and current output as arguments
            and returns a boolean.

        name Optional[(str)]: The name of the do-while tool; defaults to the tool's
            name w/ ":do_while" appended

        description Optional[(str)]: Description of what the do-while accomplishes and it's
            condition. If not provided defaults to the wrapped tool's description.

        arguments (List[Argument]): List of arguments required by the chain.
            If not specified, the arguments will be inferred from the first step.

        examples (List[Example]): Example usage scenarios

        max_iterations (Optional[int]): Maximum number of iterations to prevent
            infinite loops. Defaults to None (unlimited).

    Note:
        If using functions instead of tools, ensure the context is passed and
        utilized correctly.
    """

    def __init__(
        self,
        tool: Union[Tool, Callable[[Context, Any], Any]],
        condition: Callable[[Context, Any], bool],
        prepare_args: Callable[[Context, Dict[str, Any]], Dict[str, Any]],
        initial_state: Optional[
            Union[
                Dict[str, Any],
                Callable[[Context, Dict[str, Any]], Dict[str, Any]],
            ]
        ] = None,
        name: Optional[str] = None,
        description: Optional[str] = None,
        arguments: Optional[List[Argument]] = None,
        examples: List[Example] = [],
        max_iterations: Optional[int] = None,
    ):
        self.condition = condition
        self.max_iterations = max_iterations
        self.prepare_args = prepare_args

        if initial_state is None:
            self.initial_state = {}
        elif isinstance(initial_state, dict):
            self.initial_state = initial_state
            self.__initial_state_fn = None
        elif callable(initial_state):
            self.initial_state = None
            self.__initial_state_fn = initial_state

        if isinstance(tool, Tool):
            self.tool = tool
        else:
            self.tool = toolify(tool)

        super().__init__(
            name=name,
            args=arguments,
            description=description,
            func=self._loop,
            examples=examples,
        )

    def _loop(self, context: Context, **kwargs) -> Any:
        if "iteration" not in context:
            context["iteration"] = 0

        if "state" not in context:
            if self.__initial_state_fn is not None:
                context["state"] = self.__initial_state_fn(context, kwargs)
            elif self.__initial_state is not None:
                context["state"] = self.__initial_state
            else:
                context["state"] = {}

        if "args" not in context:
            context["args"] = []

        while True:
            if (
                self.__max_iterations is not None
                and context["iteration"] >= self.__max_iterations
            ):
                raise ValueError("max iterations reached")

            args = self.prepare_args(context, kwargs)
            context["current_args"] = args
            context["args"].append(args)

            output = self.tool(context, **args)

            if self.condition(context, output):
                break
            else:
                context["iteration"] += 1

        return output

    def retry(self, context: Context) -> Any:
        """
        Retry the tool call. This attempts to pick up where the do-while flow
        left off in the current iteration.
        """
        if context.attached is None:
            raise ValueError("no tool assigned to context")

        if context.attached != self:
            raise ValueError(
                f"context is not for {self.name}, is instead for "
                f"{context.attached.name}"
            )

        context.clear(executing=True)

        # Since context maintains state, we can just retry the tool call
        # withe the last known state and arguments
        return self._loop(context, **context["current_args"])
