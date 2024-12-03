from abc import ABC, abstractmethod
from typing import Any, List

from agents.tools.tool import Argument, Context, Example, Tool


class Wrapper(Tool, ABC):
    """A base class for creating tool wrappers that can modify tool behavior
    through pre and post-processing.

    This abstract class allows you to wrap an existing Tool instance with
    additional functionality by implementing preprocessing before the tool's
    invocation and postprocessing after the tool's execution. This is useful
    for implementing cross-cutting concerns like validation, transformation, or
    enhancement of tool inputs/outputs.

    Args:
        name (str): The name of the wrapper tool

        description (str): A description of what the wrapper does

        tool (Tool): The original tool being wrapped

        args (List[Argument]): Additional arguments specific to the wrapper;
            these will be added to the original tool's arguments

        examples (List[Example], optional): Examples of using the wrapper.
            Defaults to [].
    """

    def __init__(
        self,
        name: str,
        description: str,
        tool: Tool,
        args: List[Argument],
        examples: List[Example] = [],
    ):
        tool_args = tool.args.copy()
        tool_args.extend(args)
        self.tool = tool

        super().__init__(name, description, tool_args, None, examples)

    @abstractmethod
    def preprocess(self, ctx: Context, **kwargs) -> Any:
        """Process the input before passing it to the wrapped tool."""
        pass

    @abstractmethod
    def postprocess(self, ctx: Context, **kwargs) -> Any:
        """Process the output from the wrapped tool."""
        pass

    def invoke(self, context: Context, **kwargs) -> Any:
        args = self.preprocess(context, **kwargs)
        results = self.tool.invoke(context, **args)
        return self.postprocess(context, results)
