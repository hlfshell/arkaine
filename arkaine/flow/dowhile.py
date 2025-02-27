from typing import Any, Callable, Dict, List, Optional, Union

from arkaine.tools.argument import Argument
from arkaine.tools.tool import Context, Example, Tool
from arkaine.tools.toolify import toolify


class DoWhile(Tool):
    """
    A tool that executes a sequence of steps repeatedly while a condition is
    met. The condition is evaluated after each iteration, ensuring the steps are
    executed at least once.

    The pseudocode flow of do while is thus, assuming the tool is called Foo,
    and our do while wrapper is called dw:

    dw(context, arguments):
        continue = True
        while(continue):
            arguments = prepare_args(context, args, output)
            output = Foo(context, arguments)

            continue = condition(context, output

            if not continue:
                break

        if format_output is not None:
            return format_output(context, output)

        return output

    The context of the do while has the following state keys maintained within
    it during do while execution that may be useful to utilize in prepare_args
    or the condition function:

    context["x"]:
        - iteration: The current iteration number
        - args: A list of each set of arguments passed to the tool for each
            iteration, starting with the initial arguments the tool was called
            with.
        - outputs: A list of the outputs of the tool for each iteration

    Args:
        tool (Tool): The tool to repeatedly trigger

        stop_condition (Callable[[Context, Any], bool]): Function that evaluates
            whether to continue the loop. Takes the context and current output
            as arguments and returns a boolean.

        args (Optional[List[Argument]]): A list of arguments the dowhile tool
            accepts. Note that if not provided, the tool's arguments will be
            utilized. If you change the arguments, you *must* also use
            prepare_args to adjust the arguments for the wrapped tool
            appropriately.

        prepare_args (Callable[[Context, Dict[str, Any]], Dict[str, Any]]):
            Function that prepares the arguments for the tool call. Takes the
            context and current arguments and returns a dictionary of arguments.

        format_output (Optional[Callable[[Context, Any], Any]]): Function that
            formats the output of the tool. Takes the context and output and
            returns a formatted output.

        name Optional[(str)]: The name of the do-while tool; defaults to the
            tool's name w/ ":do_while" appended

        description Optional[(str)]: Description of what the do-while
            accomplishes and it's condition. If not provided defaults to the
            wrapped tool's description.

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
        stop_condition: Callable[[Context, Any], bool],
        prepare_args: Optional[
            Callable[[Context, Dict[str, Any]], Dict[str, Any]]
        ],
        args: Optional[List[Argument]] = None,
        format_output: Optional[Callable[[Context, Any], Any]] = None,
        name: Optional[str] = None,
        description: Optional[str] = None,
        examples: List[Example] = [],
        max_iterations: Optional[int] = None,
        id: Optional[str] = None,
    ):
        self.stop_condition = stop_condition
        self.max_iterations = max_iterations
        self.prepare_args = prepare_args
        self.format_output = format_output

        if isinstance(tool, Tool):
            self.tool = tool
        else:
            self.tool = toolify(tool)

        # Use default name if none provided
        if name is None:
            name = f"{self.tool.name}:do_while"

        # Use tool's description if none provided
        if description is None:
            description = (
                f"Repeatedly executes {self.tool.name} until condition is "
                f"met. Inherits arguments from {self.tool.name}."
            )

        if args is not None and len(args) > 0:
            if self.prepare_args is None:
                raise ValueError(
                    "prepare_args must be provided if args are provided"
                )
            args = args
        else:
            args = self.tool.args

        super().__init__(
            name=name,
            args=args,
            description=description,
            func=self._loop,
            examples=examples,
            id=id,
        )

    def _loop(self, context: Context, **kwargs) -> Any:
        args = kwargs

        context.init("args", [])
        context.init("outputs", [])

        while True:
            context.init("iteration", 0)
            context.increment("iteration", 1)

            if (
                self.max_iterations is not None
                and context["iteration"] > self.max_iterations
            ):
                raise ValueError("max iterations surpassed")

            if self.prepare_args is not None:
                args = self.prepare_args(context, args)

            context.append("args", args)

            output = self.tool(context, **args)

            context.append("outputs", output)

            if self.stop_condition(context, output):
                break

        if self.format_output is not None:
            return self.format_output(context, output)

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
        return self._loop(context, **context["args"][-1])
