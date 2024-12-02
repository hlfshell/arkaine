from agents.tools.tool import Context, Tool, Argument, Example

from typing import Any, List, Optional, Callable


class Linear(Tool):
    """
    A tool that chains multiple tools together in a sequential pipeline.

    This tool executes a series of tools in sequence, with optional formatting
    between steps. Each tool's output becomes the input for the next tool in
    the chain. Optional formatters can transform the output of each step before
    it's passed to the next tool, including the final step.

    Args:
        name (str): The name of the linear chain tool
        description (str): A description of what the chain accomplishes
        arguments (List[Argument]): List of arguments required by the chain
        examples (List[Example]): Example usage scenarios for the chain
        steps (List[Tool]): Ordered list of tools to execute in sequence
        formatters (List[Optional[Callable[[Context, Any], Any]]]): List of
            formatter functions that can transform the output between steps.
            Should be the same length as steps. Use None for steps that don't
            need formatting. Typically you want to format the output to ensure
            it's a dict of variables for the next tool.

    Example:
        ```python
        new_tool = Linear(
            name="summarize_and_translate",
            description="Summarizes text then translates it",
            arguments=[Argument(name="text", type="str", required=True)],
            examples=[Example(input="Long text...", output="Short summary in Spanish")],
            steps=[summarizer_tool, translator_tool],
            formatters=[None, None]
        )
        ```
    """

    def __init__(
        self,
        name: str,
        description: str,
        arguments: List[Argument],
        examples: List[Example],
        steps: List[Tool],
        formatters: List[Optional[Callable[[Context, Any], Any]]],
    ):
        self.steps = steps
        self.formatters = formatters

    def invoke(self, context: Context, **kwargs) -> Any:
        output = kwargs
        for step, formatter in zip(self.steps, self.formatters):
            output = step(context=context, **output)
            if formatter:
                output = formatter(context, output)
        return output
