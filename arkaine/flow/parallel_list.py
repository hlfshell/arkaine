from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import (
    Any,
    Callable,
    Dict,
    List,
    Optional,
    Union,
)

from arkaine.tools.toolify import toolify
from arkaine.tools.events import ToolReturn
from arkaine.tools.tool import (
    Context,
    ToolArguments,
    Tool,
    InvalidArgumentException,
)


class ParallelList(Tool):
    """A wrapper that executes a tool in parallel across a list of inputs.

    This tool takes a list of inputs and runs the wrapped tool for each item
    concurrently. The results can optionally be formatted using a custom
    formatter via the result_formatter argument, allowing you to customize
    the output of the tool to make it easier to feed its output into others.

    When calling a parallel_list tool, there are several accepted formats to
    call it, depending on the wrapped tool's arguments. Assuming that we have a
    tool with two arguments, a, and b, you can call it the following ways:

    1. A list of dicts
    results = tool([{"a": 1, "b": 2}, {"a": 3, "b": 4}])

    2. Mixed lists and individual arguments
    results = tool("hello", ["world", "Abby", "Clem Fandango"])

    3. A dict of lists
    results = tool({"a": [1, 3, 5], "b": [2, 4, 6]})

    4 A list of lists (corresponding to the arguments)
    results = tool([[1, 2], [3, 4]])

    5 Individual lists
    results = tool([1, 2, 3], [4, 5, 6])

    Note that whenever passing lists, the lengths must be the same, or
    a ValueError will be raised. When passing an individual variable,
    it will be assumed that this argument should be the same for each
    input. Note that if the singular value is a list itself, there may
    be issues. When in doubt, default to a list of dicts.

    As an additional helper (to make argument names more flexible),
    parallel list also accepts pluralized names of arguments. For example,
    if an argument is named "resource", "resources" will also be accepted
    *assuming the argument name is not already in use*. Similarly common
    pluralization is handled - so "leaf" would accept "leaves", "knife"
    would accept "knives", and so on. This doesn't work for more unique
    naming schemes however (mouse -> mice).

    Args:
        tool (Tool): The base tool to wrap and execute for each input
        result_formatter (Optional[Callable[[Context, List[Any]], Any]]):
            Optional function to format the combined results. If not provided,
            returns the list of results. Note that the list of results is
            provided in the same order as the input. If the error strategy is to
            ignore errors, the list of results will still be the same size as
            the input, but with an Exception object in the place of the result
            for each item that failed. If the completion strategy is for "n" or
            "any", the list of results will contain None for each input that was
            not completed but didn't fail.
        max_workers (Optional[int]): Maximum number of concurrent executions.
        completion_strategy (str): How to handle completion:
            - "all": Wait for all items (default)
            - "any": Return after first successful completion
            - "n": Return after N successful completions
            - "majority": Return after majority of items complete
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
        tool: Union[Tool, Callable[[Context, Any], Any]],
        result_formatter: Optional[Callable[[List[Any]], Any]] = None,
        max_workers: Optional[int] = None,
        completion_strategy: str = "all",
        completion_count: Optional[int] = None,
        error_strategy: str = "fail",
        name: Optional[str] = None,
        description: Optional[str] = None,
    ):
        if isinstance(tool, Tool):
            self.tool = tool
        else:
            self.tool = toolify(tool)

        if completion_strategy not in ["all", "any", "n", "majority"]:
            raise ValueError(
                "completion_strategy must be one of: all, any, n, majority"
            )

        if completion_strategy == "n" and not completion_count:
            raise ValueError(
                "completion_count required when completion_strategy is 'n'"
            )

        if error_strategy not in ["ignore", "fail"]:
            raise ValueError("error_strategy must be one of: ignore, fail")

        # self._args_transform = args_transform
        self._result_formatter = result_formatter
        self._completion_strategy = completion_strategy
        self._completion_count = completion_count
        self._error_strategy = error_strategy
        self._threadpool = ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix=f"{name or self.tool.name}::parallel",
        )

        if not name:
            name = f"{self.tool.name}::parallel_list"

        if not description:
            description = (
                f"Executes {self.tool.name} in parallel across a list of "
                f"inputs. {self.tool.name} is:\n{self.tool.description}"
            )

        super().__init__(
            name=name,
            description=description,
            args=self.tool.args,
            func=self.parallelize,
            examples=self.tool.examples,
        )

    def _allowed_names(self) -> Dict[str, str]:
        """Returns a mapping of allowed name variations to their canonical
        argument names.

        For example, if an argument is named "resource", the mapping will
        include: {"resources": "resource", "resource": "resource"}
        """
        name_mapping = {}
        for arg in self.args:
            name = arg.name
            name_mapping[name] = name  # canonical name maps to itself

            # Basic pluralization rules
            new_name = None
            if name.endswith("y"):
                new_name = name[:-1] + "ies"  # category -> categories
            elif (
                name.endswith("ch") or name.endswith("sh") or name.endswith("x")
            ):
                new_name = name + "es"  # match -> matches
            elif name.endswith("f"):
                new_name = name[:-1] + "ves"  # leaf -> leaves
            elif name.endswith("fe"):
                new_name = name[:-2] + "ves"  # knife -> knives
            else:
                new_name = name + "s"  # cat -> cats

            # We don't want to override existing arguments
            if new_name and new_name not in name_mapping:
                name_mapping[new_name] = name

        return name_mapping

    def extract_arguments(self, args, kwargs):
        # Extract context if present as first argument
        context = None
        if args and isinstance(args[0], Context):
            context = args[0]
            args = args[1:]  # Remove context from args

        # Handle tuple case - if we have a single tuple argument, try to map it
        # to the tool's arguments
        if len(args) == 1 and isinstance(args[0], tuple):
            tuple_args = args[0]
            # If the number of tuple items matches our expected arguments,
            # unpack it
            if len(tuple_args) == len(self.tool.args):
                kwargs = {
                    arg.name: value
                    for arg, value in zip(self.tool.args, tuple_args)
                }
                args = ()
            else:
                # If not matching, treat it as a single argument for the first
                # parameter
                kwargs = {self.tool.args[0].name: args[0]}
                args = ()

        # Handle single dict argument case
        elif len(args) == 1 and not kwargs and isinstance(args[0], dict):
            kwargs = args[0]
            args = ()

        # Map remaining positional args to their parameter names
        tool_args = [arg.name for arg in self.tool.args]
        for i, value in enumerate(args):
            if i < len(tool_args):
                if tool_args[i] in kwargs:
                    raise TypeError(
                        f"Got multiple values for argument '{tool_args[i]}'"
                    )
                kwargs[tool_args[i]] = value

        # Now we go ahead and build a list of dict inputs based on the arguments
        name_mapping = self._allowed_names()

        # Check if any kwargs values are lists
        list_lengths = set()
        list_args = {}
        non_list_args = {}

        for key, value in kwargs.items():
            if key not in name_mapping:
                raise ValueError(f"Invalid argument: {key}")

            # Map to canonical name
            canonical_name = name_mapping[key]

            if isinstance(value, list):
                list_args[canonical_name] = value
                list_lengths.add(len(value))
            else:
                non_list_args[canonical_name] = value

        # Initialize input_list
        input_list = []

        # If we found lists, validate lengths and create input dicts
        if list_args:
            if len(list_lengths) > 1:
                raise ValueError(
                    "All arguments that are lists must be the same length"
                )

            length = list_lengths.pop()

            for i in range(length):
                input_dict = non_list_args.copy()
                for key, value in list_args.items():
                    # Remove pluralization if present
                    singular_key = key[:-1] if key[-1] == "s" else key
                    if singular_key in name_mapping:
                        input_dict[singular_key] = value[i]
                    else:
                        input_dict[key] = value[i]
                input_list.append(input_dict)
        else:
            # If no lists found, treat the entire kwargs as a single input
            input_list = [kwargs]

        # Return in the expected format
        return context, {"input": input_list}

    def check_arguments(self, args: ToolArguments):
        # First verify we have the input key
        if "input" not in args:
            raise InvalidArgumentException(
                tool_name=self.name,
                missing_required_args=["input"],
                extraneous_args=[],
            )

        input_list = args["input"]
        if not isinstance(input_list, list):
            raise ValueError(
                f"Expected list for 'input', got {type(input_list)}"
            )

        # For each input dict, validate against the wrapped tool's arguments
        tool_arg_names = {arg.name for arg in self.tool.args}

        for i, input_dict in enumerate(input_list):
            missing_args = []
            extraneous_args = []

            # Check for extraneous arguments
            for arg_name in input_dict:
                if arg_name not in tool_arg_names:
                    extraneous_args.append(arg_name)

            # Check for missing required arguments
            for arg in self.tool.args:
                if arg.required and arg.name not in input_dict:
                    missing_args.append(arg.name)

            if missing_args or extraneous_args:
                raise InvalidArgumentException(
                    tool_name=f"{self.name}[{i}]",
                    missing_required_args=missing_args,
                    extraneous_args=extraneous_args,
                )

    def parallelize(
        self, context: Context, input: List[Dict[str, Any]]
    ) -> List[Any]:
        # Fire off the tool in parallel with the executor for each input
        # Store in a dict for direct reference
        futures_dict = {}
        for idx, kwargs in enumerate(input):
            future = self._threadpool.submit(self.tool, context, **kwargs)
            futures_dict[future] = idx

        # Based on the completion strategy, handle the futures
        context["results"] = [None] * len(input)
        if self._completion_strategy == "all":
            for future in as_completed(futures_dict):
                idx = futures_dict[future]
                try:
                    context["results"][idx] = future.result()
                except Exception as e:
                    if self._error_strategy == "fail":
                        raise e
                    else:
                        context["results"][idx] = e
        elif self._completion_strategy == "any":
            # Wait for any future to complete
            future = next(as_completed(futures_dict))
            idx = futures_dict[future]
            try:
                context["results"][idx] = future.result()
            except Exception as e:
                if self._error_strategy == "fail":
                    raise e
                else:
                    context["results"][idx] = e
            # Cancel all other futures
            for future in futures_dict:
                if future != next:
                    future.cancel()
        elif (
            self._completion_strategy == "n"
            or self._completion_strategy == "majority"
        ):
            # Wait for N futures to complete
            remaining_futures = set(futures_dict.keys())

            # to_complete is utilized if the context already has a
            # "to_go_count", which is set within retries. It alerts us to there
            # being some number of output already complete, and thus we need to
            # make it to the completion count including these.
            if self._completion_strategy == "n":
                to_complete = (
                    context["to_go_count"]
                    if "to_go_count" in context
                    else self._completion_count
                )
            elif self._completion_strategy == "majority":
                to_complete = (
                    context["to_go_count"]
                    if "to_go_count" in context
                    else len(remaining_futures) // 2
                )

            completed = 0
            while completed < to_complete and remaining_futures:
                future = next(as_completed(remaining_futures))
                idx = futures_dict[future]
                try:
                    context["results"][idx] = future.result()
                except Exception as e:
                    if self._error_strategy == "fail":
                        raise e
                    else:
                        context["results"][idx] = e
                completed += 1
                remaining_futures.remove(future)

            # Cancel all other futures
            for future in remaining_futures:
                future.cancel()

        # Format the results if a formatter is provided
        if self._result_formatter:
            return self._result_formatter(context, context["results"])
        else:
            return context["results"].copy()

    def retry(self, context: Context) -> Any:
        """
        Retry the parallel list execution. This attempts to retry only the
        failed items from the previous execution.
        """
        # Ensure that the context passed is in fact a context for this tool
        if context.attached is None:
            raise ValueError("no tool assigned to context")
        if context.attached != self:
            raise ValueError(
                f"context is not for {self.name}, is instead for "
                f"{context.attached.name}"
            )

        # Get the original args and clear the context for re-running
        args = context.args.copy()
        input_list = args["input"]
        original_results = context["results"]
        context.clear(executing=True)

        with context:
            # Figure out which items failed in context["result"] - we create a
            # new list of outputs that only includes the failed/incomplete
            # items.
            failed_indices = [
                idx
                for idx, result in enumerate(context["results"])
                if result is None or isinstance(result, Exception)
            ]

            # Create a new list of inputs that only includes the failed items
            input_list = [input_list[idx] for idx in failed_indices]

            # We need to tell the paralellize function through the context that
            # *this* particular context already has a set amount complete.
            # Since we are clearing the results["output"], we can't count it
            # without setting it as an optional override.
            if self._completion_strategy == "n":
                context["to_go_count"] = self._completion_count - sum(
                    1
                    for result in context["results"]
                    if result is not None and not isinstance(result, Exception)
                )
            elif self._completion_strategy == "majority":
                context["to_go_count"] = (
                    (len(input_list) // 2)
                    + 1
                    - sum(
                        1
                        for result in context["results"]
                        if result is not None
                        and not isinstance(result, Exception)
                    )
                )

            output = self.parallelize(
                context,
                input_list,
            )

            context["results"] = original_results

            # Now that we have the results for the failed indexes,
            # we need to now set these results to their corresponding
            # indexes in the original context["results"] list.
            for new_idx, old_idx in enumerate(failed_indices):
                context["results"][old_idx] = output[new_idx]

            context.output = context["results"]
            context.broadcast(ToolReturn(context["results"]))

            return context["results"]

    def __del__(self):
        self._threadpool.shutdown(wait=False)
