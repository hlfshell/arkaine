import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable, Dict, Iterable, List, Optional

from agents.tools.tool import Argument, Context, Tool
from agents.tools.wrapper import Wrapper


class ParallelList(Tool):
    """A wrapper that executes a tool in parallel across a list of inputs.

    This tool takes a list of inputs and runs the wrapped tool for each item
    concurrently. Each input can be optionally formatted before being passed to
    the tool, and the final results can be aggregated using a custom formatter.

    Args:
        tool (Tool): The base tool to wrap and execute for each input
        arguments (Optional[List[Argument]]): A list of arguments to present
            as input for the tool. If not provided, the tool's arguments are
            presented in the description of a singular argument, "input". It
            will describe the input as a list of items, each of which is a
            dictionary with the keys and values corresponding to the tool's
            arguments. Required and default arguments are described.
        item_formatter (Optional[Callable[[Any], Any]]): Optional
            function to format each list item into the kwargs expected by the
            wrapped tool. If not provided, each item is passed directly as the
            argument specified by list_argument.
        result_formatter (Optional[Callable[[List[Any]], Any]]): Optional
            function to format the combined results. If not provided, returns
            the list of results. Note that the list of results is provided in
            the same order as the input. If the error strategy is to ignore
            errors, the list of results will still be the same size as the
            input, but with an Exception object in the place of the result for
            each item that failed. If the completion strategy is for "n" or
            "any", the list of results will contain None for each input that
            was not completed but didn't fail.
        max_workers (Optional[int]): Maximum number of concurrent executions.
        completion_strategy (str): How to handle completion:
            - "all": Wait for all items (default)
            - "any": Return after first successful completion
            - "n": Return after N successful completions
        completion_count (Optional[int]): Required when completion_strategy="n";
            # of successful completions to wait for.
        error_strategy (str): How to handle errors:
            - "ignore": Continue execution (default)
            - "fail": Stop all execution on first error
            Defaults to "fail"
        name (Optional[str]): Custom name for the wrapper. Defaults to
            "{tool.name}::parallel_list"
        description (Optional[str]): Custom description. Defaults to describing
            the parallel execution behavior and then the wrapped tool's
            description.
    """

    def __init__(
        self,
        tool: Tool,
        arguments: Optional[List[Argument]] = None,
        item_formatter: Optional[Callable[[Any], Any]] = None,
        result_formatter: Optional[Callable[[List[Any]], Any]] = None,
        max_workers: Optional[int] = None,
        completion_strategy: str = "all",
        completion_count: Optional[int] = None,
        error_strategy: str = "fail",
        name: Optional[str] = None,
        description: Optional[str] = None,
    ):
        if completion_strategy not in ["all", "any", "n"]:
            raise ValueError("completion_strategy must be one of: all, any, n")

        if completion_strategy == "n" and not completion_count:
            raise ValueError(
                "completion_count required when completion_strategy is 'n'"
            )

        if error_strategy not in ["ignore", "fail"]:
            raise ValueError("error_strategy must be one of: ignore, fail")

        self._item_formatter = item_formatter
        self._result_formatter = result_formatter
        self._completion_strategy = completion_strategy
        self._completion_count = completion_count
        self._error_strategy = error_strategy
        self._threadpool = ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix=f"{name or tool.name}::parallel",
        )

        if not name:
            name = f"{tool.name}::parallel_list"

        if not description:
            description = (
                f"Executes {tool.name} in parallel across a list of inputs. "
                f"{tool.name} is:\n{tool.description}"
            )

        self.tool = tool

        if arguments:
            args = arguments
        else:
            # Build the list of arguments argument based on the tool's
            # argument's descriptions
            list_arg_description = (
                "A list wherein each item consists of the following:"
            )
            for arg in tool.args:
                list_arg_description += f"\n- {arg.name} ({arg.type})"
                if arg.required:
                    list_arg_description += f"[required] "
                list_arg_description += f": {arg.description}"
                if arg.default:
                    list_arg_description += f" (default: {arg.default})\n"

            args = [
                Argument(
                    name="input",
                    description=list_arg_description,
                    type="list",
                    required=True,
                )
            ]

        super().__init__(
            name=name,
            description=description,
            args=args,
            func=self.parallelize,
            examples=tool.examples,
        )

    def parallelize(self, context: Context, **kwargs) -> List[Any]:
        input = kwargs[self.args[0].name]

        if not isinstance(input, Iterable):
            raise ValueError(
                f"The input argument must be an iterable, got {type(input)}"
            )

        if self._item_formatter:
            input = [self._item_formatter(item) for item in input]

        # Fire off the tool in parallel with the executor for each input
        futures = {
            # self._threadpool.submit(self.tool.invoke, context, **kwargs): idx
            self._threadpool.submit(self.tool, context, **kwargs): idx
            for idx, kwargs in enumerate(input)
        }

        # Based on the completion strategy, handle the futures
        results = [None] * len(input)
        if self._completion_strategy == "all":
            for future in as_completed(futures):
                idx = futures[future]
                try:
                    results[idx] = future.result()
                except Exception as e:
                    if self._error_strategy == "fail":
                        raise e
                    else:
                        results[idx] = e
        elif self._completion_strategy == "any":
            # Wait for any future to complete
            future = next(as_completed(futures))
            idx = futures[future]
            try:
                results[idx] = future.result()
            except Exception as e:
                if self._error_strategy == "fail":
                    raise e
                else:
                    results[idx] = e
            # Cancel all other futures
            for future in futures:
                future.cancel()
        elif self._completion_strategy == "n":
            # Wait for N futures to complete
            for _ in range(self._completion_count):
                future = next(as_completed(futures))
                idx = futures[future]
                try:
                    results[idx] = future.result()
                except Exception as e:
                    if self._error_strategy == "fail":
                        raise e
                    else:
                        results[idx] = e
            # Cancel all other futures
            for future in futures:
                future.cancel()

        # Format the results if a formatter is provided
        if self._result_formatter:
            return self._result_formatter(results)
        return results

    def __del__(self):
        self._threadpool.shutdown(wait=False)
