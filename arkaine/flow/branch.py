from concurrent.futures import as_completed
from typing import Any, Callable, List, Optional, Union

from arkaine.tools.tool import Argument, Context, Example, Tool


class Branch(Tool):
    """
    A tool that executes multiple tools or functions in parallel and aggregates
    their results.

    This tool takes an input and runs it through multiple tools or functions
    concurrently. It provides options for handling failures and different
    completion strategies, as well as methods to transform the input for each
    tool and the combination of the tool's output.

    Args:
        name (str): The name of the branch tool

        description (str): Description of what the branch accomplishes

        arguments (List[Argument]): List of arguments required by the branch

        examples (List[Example]): Example usage scenarios

        tools (List[Union[Tool, Callable[[Context, Any], Any]]]): List of tools
            or functions to execute in parallel

        formatters (List[Optional[Callable[[Context, Any], Any]]]): Optional
            formatters to transform input for each branch. The index of the
            formatter should match the index of the tool.

        completion_strategy (str): How to handle branch completion:
            - "all": Wait for all branches (default)
            - "any": Return as soon as any branch completes
            - "n": Wait for n branches to complete
            - "majority": Return when majority of branches complete

        error_strategy (str): How to handle branch failures:
            - "ignore": Continue execution (default)
            - "fail": Fail entire branch if any tool fails

        result_formatter (Optional[Callable[[List[Any], List[Exception]],
        Any]]): Optional
            function to format the combined results of all branches. The
            formatter will receive a list of results from each branch, with the
            index of the result matching the index of the tool that produced
            it. It will also be passed the exception if any was raised (which,
            depending on your error strategy, may be ignored).

        id (Optional[str]): The unique identifier for the tool; defaults to a
            random UUID.

    Note:
        If using functions instead of tools, ensure the context is passed and
        utilized correctly.
    """

    def __init__(
        self,
        name: str,
        description: str,
        arguments: List[Argument],
        examples: List[Example],
        tools: List[Union[Tool, Callable[[Context, Any], Any]]],
        formatters: Optional[
            List[Optional[Callable[[Context, Any], Any]]]
        ] = None,
        completion_strategy: str = "all",
        completion_count: Optional[int] = None,
        error_strategy: str = "ignore",
        result_formatter: Optional[
            Callable[[List[Any], List[Exception]], Any]
        ] = None,
        id: Optional[str] = None,
    ):
        self.tools = tools
        self.formatters = formatters or [None] * len(tools)
        if completion_strategy not in ["all", "any", "n", "majority"]:
            raise ValueError(
                "completion_strategy must be one of: all, any, n, majority"
            )
        self.completion_strategy = completion_strategy
        if completion_strategy == "n" and completion_count is None:
            raise ValueError("completion_count must be provided if n is used")
        self.completion_count = completion_count

        self.error_strategy = error_strategy
        self.result_formatter = result_formatter

        if len(self.formatters) != len(tools):
            raise ValueError(
                "Number of formatters must match number of branches"
            )

        super().__init__(
            name=name,
            args=arguments,
            description=description,
            func=None,
            examples=examples,
            id=id,
        )

    def __required_completions(self, context: Context) -> int:
        return {
            "all": len(self.tools),
            "any": 1,
            "majority": (len(self.tools) // 2) + 1,
            "n": self.completion_count,
        }[self.completion_strategy]

    def invoke(self, context: Context, **kwargs) -> Any:
        if "results" not in context:
            context["results"] = [None] * len(self.tools)
        if "completed" not in context:
            context["completed"] = 0
        if "errors" not in context:
            context["errors"] = [None] * len(self.tools)

        # Create a dictionary mapping futures to their indices
        future_map = {
            tool.async_call(
                context=context,
                **(
                    kwargs.copy()
                    if formatter is None
                    else formatter(context, kwargs.copy())
                ),
            ).future(): index
            for index, (tool, formatter) in enumerate(
                zip(self.tools, self.formatters)
            )
        }

        required_completions = self.__required_completions(context)

        for future in as_completed(future_map.keys()):
            index = future_map[future]
            try:
                result = future.result()
                context["results"][index] = result
                context.increment("completed")
                if context["completed"] >= required_completions:
                    # Cancel remaining futures if we've met our completion
                    # criteria
                    for f in future_map.keys():
                        if not f.done():
                            f.cancel()
                    break
            except Exception as e:
                context["errors"][index] = e
                context.increment("completed")
                if self.error_strategy == "fail":
                    raise e

        if self.result_formatter:
            return self.result_formatter(context["results"], context["errors"])
        return context["results"]

    def retry(self, context: Context) -> Any:
        """
        Retry the branch execution. This attempts to retry only the failed
        branches from the previous execution.
        """
        if context.attached is None:
            raise ValueError("no tool assigned to context")
        elif not isinstance(context.attached, Tool):
            raise ValueError(
                "context.attached must be an instance of Tool, got "
                f"{type(context.attached)}"
            )

        if context.attached != self:
            raise ValueError(
                f"context is not for {self.name}, is instead for "
                f"{context.attached.name}"
            )

        original_args = context.args
        context.clear()

        # If we have no children, we never branched, and thus we need to
        # just recall this tool with the last args
        if len(context.children) == 0:
            return self(context, **original_args)

        # Identify which branches have no input or have errors.
        failed_indices = [
            idx
            for idx, (result, error) in enumerate(
                zip(context["results"], context["errors"])
            )
            if result is None or error is not None
        ]

        # Reset context["completed"] to only include the successful branches
        context["completed"] = len(context["results"]) - len(failed_indices)

        # Clear existing errors
        context["errors"] = [None] * len(context["results"])

        # Determine how many we need to complete
        required_completions = (
            self.__required_completions(context) - context["completed"]
        )
        # We track completions separately from context["completed"] because
        # context["completed"] includes previously successful completions.
        completed = 0

        # For each child in the failed indices, we need to retry the tool
        # with its passed args
        with context:
            for idx in failed_indices:
                child_ctx = context.children[idx]
                try:
                    result = child_ctx.attached.retry(child_ctx)
                    context["results"][idx] = result
                    completed += 1
                    context.increment("completed")
                    if completed >= required_completions:
                        break
                except Exception as e:
                    context["errors"][idx] = e
                    completed += 1
                    context.increment("completed")
                    if self.error_strategy == "fail":
                        raise e

            if self.result_formatter:
                return self.result_formatter(
                    context["results"], context["errors"]
                )
            return context["results"]
