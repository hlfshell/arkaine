from typing import Any, Callable, List, Optional, Union

from arkaine.tools.events import ToolReturn
from arkaine.tools.tool import Argument, Context, Example, Result, Tool
from arkaine.tools.toolify import toolify


class Linear(Tool):
    """
    A tool that chains multiple tools or functions together in a sequential
    pipeline.

    This tool executes a series of tools or functions in sequence, with
    optional formatting between steps. Each tool's or function's output becomes
    the input for the next in the chain. Optional formatters can transform the
    output of each step before it's passed to the next, including the final
    step.

    Args:
        name (str): The name of the linear chain tool

        description (str): A description of what the chain accomplishes

        arguments (List[Argument]): List of arguments required by the chain.
            If not specified, the arguments will be inferred from the first
            step.

        examples (List[Example]): Example usage scenarios for the chain

        steps (List[Union[Tool, Callable[[Context, Any], Any]]]): Ordered list
            of tools or functions to execute in sequence

        formatters (List[Optional[Callable[[Context, Any], Any]]]): List of
            formatter functions that can transform the output between steps.
            Should be the same length as steps or one additional. Use None for
            steps that don't need formatting. Typically you want to format the
            output to ensure it's a dict of variables for the next tool. In
            terms of indexing, the formatter is called PRIOR to the
            equivalently indexed step. If the index is +1 of the size of the
            steps list, this final formatter is called AFTER the last step and
            returned.

    Note:
        If using functions instead of tools, ensure the context is passed and
        utilized correctly, and that the function returns a Context as well.
    """

    def __init__(
        self,
        name: str,
        description: str,
        arguments: Optional[List[Argument]],
        steps: List[Union[Tool, Callable[[Context, Any], Any]]],
        examples: List[Example] = [],
        result: Optional[Result] = None,
        id: Optional[str] = None,
    ):
        self.steps = [
            step if isinstance(step, Tool) else toolify(step) for step in steps
        ]

        if arguments is None:
            arguments = steps[0].args

        super().__init__(
            name=name,
            args=arguments,
            description=description,
            func=self.invoke,
            examples=examples,
            result=result,
            id=id,
        )

    def invoke(self, context: Context, **kwargs) -> Any:
        output = kwargs
        context.x["init_input"] = output

        if "step" not in context:
            context["step"] = 0

        for index, step in enumerate(self.steps):
            if index < context["step"]:
                continue
            context["step"] = index

            try:
                output = step(context, output)
            except Exception as e:
                raise StepException(e, index) from e

        return output

    def retry(self, context: Context) -> Any:
        """
        Retry the tool call. This attempts to pick up where the linear flow
        left off.
        """
        if context.attached is None:
            raise ValueError("no tool assigned to context")

        if context.attached != self:
            raise ValueError(
                f"context is not for {self.name}, is instead for "
                f"{context.attached.name}"
            )

        context.clear(executing=True)

        # Find the child context that failed OR failed to generate an output
        # (this would simply be interrupted from somewhere else), and clear it.
        # This is where we will launch from.
        for index, child in enumerate(context.children):
            if child.exception or not child.output:
                child.clear(args=child.args)

        with child:
            context["step"] = index
            output = self.steps[index].retry(child)
            context.increment("step")
            _, output = self.extract_arguments((context, output), {})

        with context:
            results = self.invoke(context, **output)
            context.output = results
            context.broadcast(ToolReturn(results))
            return results


class StepException(Exception):
    def __init__(self, exception: Exception, index: int):
        self.exception = exception
        self.index = index

    def __str__(self):
        return f"Error in step {self.index}: {str(self.exception)}"
