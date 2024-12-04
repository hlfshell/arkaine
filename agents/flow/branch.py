from agents.tools.tool import Context, Tool, Argument, Example
from typing import Any, List, Optional, Callable
from concurrent.futures import as_completed
import threading


class Branch(Tool):
    """
    A tool that executes multiple tools in parallel and aggregates their
    results.

    This tool takes an input and runs it through multiple tools concurrently.
    It provides options for handling failures and different completion
    strategies, as well as methods to transform the input for each tool and the
    combination of the tool's output.

    Args:
        name (str): The name of the branch tool

        description (str): Description of what the branch accomplishes

        arguments (List[Argument]): List of arguments required by the branch

        examples (List[Example]): Example usage scenarios

        tools (List[Tool]): List of tools to execute in parallel

        formatters (List[Optional[Callable[[Context, Any], Any]]]): Optional
            formatters to transform input for each branch. The index of the
            formatter should match the index of the tool.

        completion_strategy (str): How to handle branch completion:
            - "all": Wait for all branches (default)
            - "any": Return as soon as any branch completes
            - "majority": Return when majority of branches complete

        error_strategy (str): How to handle branch failures:
            - "ignore": Continue execution (default)
            - "fail": Fail entire branch if any tool fails

        result_formatter (Optional[Callable[[List[Any],
            List[Exception]], Any]]): Optional function to format the combined
            results of all branches. The formatter will receive a list of
            results from each branch, with the index of the result matching the
            index of the tool that produced it. It will also be passed the
            exception if any was raised (which, depending on your error
            strategy, may be ignored).
    """

    def __init__(
        self,
        name: str,
        description: str,
        arguments: List[Argument],
        examples: List[Example],
        tools: List[Tool],
        formatters: Optional[
            List[Optional[Callable[[Context, Any], Any]]]
        ] = None,
        completion_strategy: str = "all",
        error_strategy: str = "ignore",
        result_formatter: Optional[
            Callable[[List[Any], List[Exception]], Any]
        ] = None,
    ):
        self.tools = tools
        self.formatters = formatters or [None] * len(tools)
        self.completion_strategy = completion_strategy
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
        )

    def invoke(self, context: Context, **kwargs) -> Any:
        results: List[Any] = [None] * len(self.tools)
        errors: List[Exception] = [None] * len(self.tools)
        completed = 0
        lock = threading.Lock()

        # Create a dictionary mapping futures to their indices
        future_map = {
            tool.async_call(
                context=context,
                **(kwargs if formatter is None else formatter(context, kwargs)),
            ).future(): index
            for index, (tool, formatter) in enumerate(
                zip(self.tools, self.formatters)
            )
        }

        required_completions = {
            "all": len(self.tools),
            "any": 1,
            "majority": (len(self.tools) // 2) + 1,
        }[self.completion_strategy]

        for future in as_completed(future_map.keys()):
            index = future_map[future]
            try:
                result = future.result()
                with lock:
                    results[index] = result
                    completed += 1
                    if completed >= required_completions:
                        # Cancel remaining futures if we've met our completion
                        # criteria
                        for f in future_map.keys():
                            if not f.done():
                                f.cancel()
                        break
            except Exception as e:
                with lock:
                    errors[index] = e
                    if self.error_strategy == "fail":
                        raise e

        if self.result_formatter:
            return self.result_formatter(results, errors)
        return results
