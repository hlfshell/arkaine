from agents.tools.tool import Context, Tool, Argument, Example

from typing import Any, List, Optional, Callable, Union


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

        arguments (List[Argument]): List of arguments required by the chain

        examples (List[Example]): Example usage scenarios for the chain

        steps (List[Union[Tool, Callable[[Context, Any], Any]]]): Ordered list
        of tools or functions to execute in sequence

        formatters (List[Optional[Callable[[Context, Any], Any]]]): List of
            formatter functions that can transform the output between steps.
            Should be the same length as steps. Use None for steps that don't
            need formatting. Typically you want to format the output to ensure
            it's a dict of variables for the next tool.

    Note:
        If using functions instead of tools, ensure the context is passed and
        utilized correctly, and that the function returns a Context as well.
    """

    def __init__(
        self,
        name: str,
        description: str,
        arguments: List[Argument],
        examples: List[Example],
        steps: List[Union[Tool, Callable[[Context, Any], Any]]],
        formatters: List[Optional[Callable[[Context, Any], Any]]],
    ):
        self.steps = steps
        self.formatters = formatters

        super().__init__(
            name=name,
            args=arguments,
            description=description,
            func=self.invoke,
            examples=examples,
        )

    def invoke(self, context: Context, **kwargs) -> Any:
        output = kwargs
        for step, formatter in zip(self.steps, self.formatters):
            if isinstance(step, Tool):
                output = step(context=context, **output)
            else:
                output = step(context, output)
            if formatter:
                output = formatter(context, output)
        return output
