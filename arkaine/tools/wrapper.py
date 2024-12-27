from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Tuple

from arkaine.tools.tool import Argument, Context, Example, Tool


class Wrapper(Tool, ABC):
    """A base class for creating tool wrappers that can modify tool behavior
    through pre and post-processing.

    This abstract class allows you to create functionality that expands the
    target Tool's capabilities by implementing pre and post processing before
    and after each invocation.

    The wrapper workflow follows these steps:

    1. preprocess(): Prepares arguments for the wrapped tool and optionally
       creates data to pass to postprocess

    2. The wrapped tool is invoked with the processed arguments

    3. postprocess(): Handles the tool's results along with any data passed
       from preprocess

    Example workflow:
        def preprocess(ctx, **kwargs):
            # Modify or validate input arguments
            processed_args = {"modified_arg": kwargs["original_arg"]}
            # Create data to pass to postprocess
            pass_through = {"original": kwargs["original_arg"]}
            return processed_args, pass_through

        def postprocess(ctx, passed, results):
            # passed contains the pass_through data from preprocess
            # results contains the output from the wrapped tool
            return f"{passed['original']} -> {results}"

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
    def preprocess(self, ctx: Context, **kwargs) -> Tuple[Dict[str, Any], Any]:
        """Process the input before passing it to the wrapped tool.

        This method should prepare the arguments for the wrapped tool and
        optionally create data to be passed to postprocess.

        Args:
            ctx (Context): The execution context
            **kwargs: The original arguments passed to the wrapper

        Returns:
            Tuple[Dict[str, Any], Any]: A tuple containing:
                - A dictionary of processed arguments to pass to the wrapped
                    tool
                - Any data that should be passed through to postprocess (can
                    be None)
        """
        pass

    @abstractmethod
    def postprocess(
        self, ctx: Context, passed: Optional[Any] = None, **kwargs
    ) -> Any:
        """Process the output from the wrapped tool.

        This method handles the results from the wrapped tool and any data
        marked to be passed from preprocess.

        Args:
            ctx (Context): The execution context
            passed (Optional[Any]): Data passed from preprocess for use in
                postprocessing
            **kwargs: The results from the wrapped tool's execution

        Returns:
            Any: The final processed result
        """
        pass

    def invoke(self, context: Context, **kwargs) -> Any:
        args, passed = self.preprocess(context, **kwargs)
        results = self.tool.invoke(context, **args)
        return self.postprocess(context, passed, results)
